#!/bin/python3

from telnetlib import Telnet
import re
from hashlib import sha512
from typing import *
from time import sleep
from os import stat, path
import yaml
import argparse
import datetime
prognameMatch = re.compile("\(\(\( filename: (.+) \)\)\)")
progDependencyMatch = re.compile("\(\(\( dependsOn: (.+) \)\)\)")
progIncludeMatch = re.compile('\(\(\( includes: (.+) as (\.\.[a-zA-Z0-9-]+) \)\)\)')
programFinder = "@find {}\n"
programFinderRegex = re.compile(b"(.+)([0-9]+):.+")
programFinderTerminator = re.compile(b'\*\*\*End of List\*\*\*')
ProgramId = re.compile(b"Program .+ created with number ([0-9]+)")
ProgramId2 = re.compile(
    b'Entering editor for .+\(#([0-9]+).+\)\.')
# Command to list content of a program, showing line numbers
programListCommand = "@list {}\n"
programListMatch = re.compile(b"\s*([0-9]+):(.+)\r\n")
programListTerminator = re.compile(b"[0-9]+ lines displayed\.")

editorInsertExitMatch = [re.compile(b"Exiting insert mode\.")]
editorCompilerStringMatch = [re.compile(b"Compiler done\."), re.compile(b"^Error in line")]
editorExitStringMatch = [re.compile(b"Editor exited\.")]

objectModifiedStringFieldMatch = \
    [
        re.compile(b"Modified: (.+) by (.+)$"),
        re.compile(b"I don't see that there\.$")
    ]
objectModificationCommand = "ex {}\n"

functionListCommand = "@listfunc {}\n"
functionListRegex = re.compile("\x1b\[[^m]*m")
# Goals:
#    Manage Dependencies:
#        Upload changed files in necessary order
#            Replacing special tokens with the correct program reference
#            Send minimal line-by-line diff in format accepted by @edit
#             and @prog
#            Provide Server-Client code synchronization when requested
#             (This will be hard to do properly in a very noisy server)
#   Provide cleanup functionality for things that totally fuck up the system


# Current stuff that needs doing
# [x] Determine if file needs to be updated due to the program being modified
#     since it was last retrieved.
# [ ] Better latency handling for the editor commands.
#    a. expect/error loop until match is found
#    b. Maybe the telnet class could do with a wrapper class
#       for handling this automatically.
# 3. 

class SyncException(Exception):
    def __init__(self, filename, remoteid):
        super(Exception, self).__init__(filename, remoteid)
        self.message = "The object with id {} associated with {}".\
            format(remoteid, filename) + \
            " could not be found"


def because_I_cant_understand_strptime(s:str):
    months = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12
    }
    m = re.compile("(Sat|Sun|Mon|Tue|Wed|Thu|Fri) " +
                   "(Jan|Feb|Mar|Apr|May|Jun|Jul" +
                   "|Aug|Sep|Oct|Nov|Dec) " +
                   "([123 ][0-9]) " +
                   "([012 ][0-9]):" +
                   "([0-5][0-9]):" +
                   "([0-5][0-9]) " +
                   "(CST|CDT) " +
                   "([0-9]+)").match(s)
    month = months[m.group(2)]
    monthday = int(m.group(3))
    hour = int(m.group(4))
    minute = int(m.group(5))
    second = int(m.group(6))
    year = int(m.group(7))
    dt = datetime.datetime(year, month, day, hour, minute, second)
    return dt

class MufFile():
    def __init__(self, filename, depth=0, parent=None, send_method="name",id=None,
                 regname=None):
        self.dependencies = []
        self.transformedname = ""
        self.filename = filename
        self.hash = sha512()
        self.length = 0
        self.parent = parent
        self.includes = {}
        self.id = id
        self.regname = regname
        self.send_method = send_method
        with open(filename) as file:
            for z in file.readlines():
                pnmatch = prognameMatch.match(z)
                if pnmatch is not None:
                    self.transformedname = pnmatch.group(1)
                    continue
                pdepmatch = progDependencyMatch.match(z)
                if pdepmatch is not None:
                    self.dependencies.append(pdepmatch.group(1))
                    continue
                pincMatch = progIncludeMatch.match(z)
                if pincMatch is not None:
                    self.includes[pincMatch.group(2)] = pincMatch.group(1)
                self.hash.update(z.encode())
                self.length += 1
        self.hash = self.hash.hexdigest()

    def send(self, tc: Telnet):
        let_be = False
        while True:
            if self.send_method == "name":
                tc.write("@prog {}\n".format(self.transformedname).encode())
            elif self.send_method == "id":
                tc.write("@prog {}\n".format(self.id).encode())
            elif self.send_method == "regname":
                print("Using regname:{0}".format(self.regname))
                tc.write("@prog {}\n".format(self.regname).encode())
            mindex, match, _ = tc.expect([ProgramId, ProgramId2], timeout=3)
            if match is not None:
                self.id = int(match.group(1))
                break
        tc.write("1 {} delete\n".format(self.length * 10).encode())
        tc.write("i\n".encode())
        counter = 0
        with open(self.filename) as fi:
            lines = fi.readlines()
            if len(lines[-1]) > 0:
                lines.append('')
            for i in lines:
                tc.write("{}".format(i).encode())
#                sleep(0.05)
                counter += 1
                print("{: =4.2}%".format(100 * counter / len(lines)),
                      end='\r', flush=True)
        print("\n", end="", flush=True)
        print("finished sending")
        while True:
            tc.write('.\n'.encode())
            index, m, _ = tc.expect(editorInsertExitMatch,
                                    timeout=5)
            if m is not None:
                break
        print("compiling program")
        while True:
            tc.write("c\n".encode())
            index, m, _ = tc.expect(editorCompilerStringMatch,
                                    timeout=7)
            if index != None and index != 1:
                let_be = True
            if m is not None:
                break
        print("quitting")
        while True:
            if let_be:
                tc.write("q\n".encode())
            else:
                tc.write("x\n".encode())
            index, m, _ = tc.expect(editorExitStringMatch,
                                    timeout=7)
            if m is not None:
                break

    @staticmethod
    def check_last_modified(filename, remoteid, tc: Telnet):
        tc.send(objectModificationCommand.format(remoteid).encode())
        idx, match, _ = tc.expect(objectModifiedStringFieldMatch)
        if idx == 1:
            raise SyncException(filename, remoteid)
        #mod_date = datetime.datetime.strptime(match.group(1),
        #                                      "%a %b %d %H:%M:%S %Z %Y")
        mod_date = because_I_cant_understand_strptime(match.group(1))
        local_stuff = path.getmtime(filename)
        return mod_date >= local_stuff

    @staticmethod
    def sync(filename, remoteid, tc: Telnet):
        tc.read_very_eager()
        tc.write(b"@set me=H\n")
        tc.write(b"pub #alloff\n")
        sleep(2)
        tc.read_very_eager()
        tc.write(programListCommand.format(remoteid).encode())
        print(programListCommand.format(remoteid))
        with open(filename, 'w') as output:
            lines = tc.read_until(b" lines displayed.").decode().split('\r\n')
            for i in lines[:-1]:
                output.write(i + '\n')
        tc.write(b"@set me=!H\n")
        tc.write(b"pub #allon\n")
        tc.read_very_eager()
#            mindex = 0
#            while mindex < 1:
#                mindex, match, _ = tc.expect([programListMatch,
#                                               programListTerminator])
#                if mindex >= 1 \
#                   or match is None:
#                    break
#                output.write(match.group(2).decode()+'\n')




# Keep track of whether or not files are up to date on the server.
class Cache():
    def __init__(self, path):
        import pickle
        self.newfiles = {}
        self.oldfiles = {}
        try:
            self = pickle.load(path + ".cache")
        except IOError:
            # probably doesn't exist
            pass

    def addFile(self, file: MufFile):
        fname = file.filename
        if fname in self.oldfiles.keys():
            if self.newfiles[fname].hash != file.hash:
                self.oldfiles[fname] = self.newfiles[fname]
                self.newfiles[fname] = file

    def syncOld(self, file: MufFile, tc: Telnet):
        tc.write(programFinder.format(file.filename))
        mindex, match, _ = tc.expect([programFinderRegex,
                                      programFinderTerminator])
        fn = None
        while match is not None and mindex != 1:
            if match.group(1) == file.transformedname:
                fn = match.group(1)
                break
            else:
                mindex, match, _ = tc.expect([programFinderRegex,
                                              programFinderTerminator])
        tc.write(programListCommand.format(fn))
        mindex = 0
        lines = []
        lastindex = 0
        while mindex != 1:
            mindex, match, _ = tc.expect([programListMatch,
                                          programListTerminator])
            if mindex != 1:
                if int(math.group(2)) != lastindex + 1:
                    print("Hmm. There might be a problem.")
                else:
                    lastindex = int(match.group(1))
                lines.append(match.group(2))


class DepGraph():
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.depths = {}
        self.validstarts = set()

    def addFile(self, file: MufFile, depth=0):
        self.nodes[file.filename] = file
        if file.filename not in self.edges.keys():
            self.edges[file.filename] = set()
            self.depths[file.filename] = depth
            if depth == 0:
                self.validstarts.add(file.filename)
        for fn in file.dependencies:
            self.edges[file.filename].add(fn)
            if fn not in self.nodes.keys():
                self.addFile(MufFile(fn, depth=depth + 1), depth + 1)

    def send(self, tc: Telnet):
        stack = list()
        path = []
        sent = set()
        for i in self.validstarts:
            stack.append(i)
            while len(stack) > 0:
                cn = stack.pop()
                if cn not in path:
                    path.append(cn)
                else:
                    continue
                for n in self.edges[cn]:
                    path.append(n)
                    stack.append(n)
            for n in reversed(path):
                print("Updating program {}".format(n))
                self.nodes[n].send(tc)

# TODO: Use a cache to check if the file needs to be uploaded again,
#  I.E. it's hash has changed.
# TODO: define a macro on the copy sent to the server such that each
#  program refers to the correct id at runtime.


# argInterpret = argparse.ArgumentParser()
# argInterpret.add_argument()
# tc = Telnet(host="localhost", port=2001)
# tc.write(b"connect one potrzebie\n")
# dg = DepGraph()
# dg.addFile(MufFile("Channel/Channel.muf"))
# dg.send(tc)
parser = argparse.ArgumentParser("Manage files on the MUCK")
parser.add_argument("--send", dest='files', action='append',
                    help='Files to send', default=[])
parser.add_argument('--sync', dest='sync', action='store_const',
                    help='Sync files?', const=True, default=False)
parser.add_argument('--send-all', dest='send_all', action='store_const',
                    help='send all files', const=True, default=False)
args = parser.parse_args()
with open('project.yaml') as projfile:
    project = yaml.load(projfile)
    print(project)
    project = project['project']
    tc = Telnet(host=project['connect']['host'],
                port=int(project['connect']['port']))
    tc.read_some()
    tc.write("connect {} {}\n".format(project['connect']['username'],
                                      project['connect']['password']).encode())
    print("connect {} {}".format(project['connect']['username'],
                                 project['connect']['password']))
    sleep(2)

    if args.sync:
        for i in project['sync']:
            if 'no_exist' in i['file'].keys() and i['file']['no_exist']:
                try:
                    stat(i['file']['name'])
                    print('skipping {}'.format(i['file']['name']))
                    continue
                except FileNotFoundError:
                    print('need to get {}'.format(i['file']['name']))
            MufFile.sync(i['file']['name'], i['file']['id'], tc)
    if args.send_all:
        for i in project['send']:
            f = None
            if 'send_method' in i['file'].keys():
                id = None
                regname = None
                print("Send method:"+i['file']['send_method'])
                if 'id' in i['file'].keys():
                    id = i['file']['id']
                if 'regname' in i['file'].keys():
                    regname = i['file']['regname']
                f = MufFile(i['file']['name'], send_method=i['file']['send_method'],
                        id=id,regname=regname)
            else:
                print("No send method found")
                f = MufFile(i['file']['name'])
            f.transformedname = i['file']['gamename']
            print("Sending " + f.transformedname)
            f.send(tc)
            sleep(1)
            print("\a")
    else:
        for i in project['send']:
            if i['file']['name'] not in args.files:
                continue
            send_with_id = False
            f = None
            if 'send_method' in i['file'].keys():
                id = None
                regname = None
                print("Send method:"+i['file']['send_method'])
                if 'id' in i['file'].keys():
                    id = i['file']['id']
                if 'regname' in i['file'].keys():
                    regname = i['file']['regname']
                f = MufFile(i['file']['name'], send_method=i['file']['send_method'],
                        id=id,regname=regname)
            else:
                f = MufFile(i['file']['name'])
            f.transformedname = i['file']['gamename']
            print("Sending " + f.transformedname)
            f.send(tc)
            sleep(1)
