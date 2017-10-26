#!/bin/python3

from telnetlib import Telnet
import re
from hashlib import sha512
from typing import *
from time import sleep
import argparse
prognameMatch = re.compile("\(\(\( filename: (.+) \)\)\)")
progDependencyMatch = re.compile("\(\(\( dependsOn: (.+) \)\)\)")
progIncludeMatch = re.compile('\(\(\( includes: (.+) as (\.\.[a-zA-Z0-9-]+) \)\)\)')
programFinder = "@find {}\n"
programFinderRegex = re.compile(b"(.+)([0-9]+):.+")
programFinderTerminator = re.compile(b'\*\*\*End of List\*\*\*')
ProgramId = re.compile(b"Program .+ created with number ([0-9]+)")
ProgramId2 = re.compile(
    b'Entering editor for .+\(#([0-9]+).+\)\.$')
# Command to list content of a program, showing line numbers
programListCommand = b"@list {}=#\n"
programListMatch = re.compile(b"^\s+([0-9]+):(.+)$")
programListTerminator = re.compile(b"[0-9]+ lines displayed\.")
# Goals:
#    Manage Dependencies:
#        Upload changed files in necessary order
#            Replacing special tokens with the correct program reference
#            Send minimal line-by-line diff in format accepted by @edit
#             and @prog
#            Provide Server-Client code synchronization when requested
#             (This will be hard to do properly in a very noisy server)
#   Provide cleanup functionality for things that totally fuck up the system


class MufFile():
    def __init__(self, filename, depth=0, parent=None):
        self.dependencies = []
        self.transformedname = ""
        self.filename = filename
        self.hash = sha512()
        self.length = 0
        self.parent = parent
        with open(filename) as file:
            for z in file.readlines():
                pnmatch = prognameMatch.match(z)
                if pnmatch is not None:
                    self.transformedname = pnmatch.group(1)
                pdepmatch = progDependencyMatch.match(z)
                if pdepmatch is not None:
                    self.dependencies.append(pdepmatch.group(1))
                self.hash.update(z.encode())
                self.length += 1
        self.hash = self.hash.hexdigest()

    def send(self, tc: Telnet):
        tc.write("@prog {}\n".format(self.transformedname).encode())
        mindex, match, _ = tc.expect([ProgramId, ProgramId2], timeout=3)
        if match is not None:
            self.id = int(match.group(1))

        tc.write("1 {} delete\n".format(self.length * 10).encode())
        tc.write("i\n".encode())
        with open(self.filename) as fi:
            for i in fi.readlines():
                tc.write("{}\n".format(i).encode())
                sleep(0.05)
        tc.write('.\n'.encode())
        tc.write("c\n".encode())
        tc.write("q\n".encode())


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

argInterpret=argparse.ArgumentParser()
argInterpret.add_argument()
tc = Telnet(host="localhost", port=2001)
tc.write(b"connect one potrzebie\n")
dg = DepGraph()
dg.addFile(MufFile("Channel/Channel.muf"))
dg.send(tc)
