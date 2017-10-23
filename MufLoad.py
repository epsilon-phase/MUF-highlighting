#!/bin/python3

import telnetlib
import re
from hashlib import sha3_512
prognameMatch = re.compile("\(\(\( filename: (.+) \)\)\)")
progDependencyMatch = re.compile("\(\(\( dependsOn: (.+) \)\)\)")
programFinder = "@find {}"
programFinderRegex = re.compile("(.+)\([0-9]+).+")
programFinderTerminator = re.compile('\*\*\*End of List\*\*\*')
ProgramId = re.compile("Program .+ created with number ([0-9]+)")
# Command to list content of a program, showing line numbers
programListCommand = "@list {}=#"
programListMatch = re.compile("^\s+([0-9]+):(.+)$")
programListTerminator = re.compile("[0-9]+ lines displayed\.")
# Goals:
#    Manage Dependencies:
#        Upload changed files in necessary order
#            Replacing special tokens with the correct program reference
#            Send minimal line-by-line diff in format accepted by @edit
#             and @prog
#            Provide Server-Client code synchronization when requested
#             (This will be hard to do properly in a very noisy server)
#   Provide cleanup functionality for things that totally fuck up the system


class File():
    def __init__(self, filename):
        self.dependencies = []
        self.transformedname = ""
        self.filename = filename
        self.hash = sha3_512()
        self.length = 0
        with open(filename) as file:
            for z in file.readlines():
                pnmatch = prognameMatch.match(z)
                if pnmatch is not None:
                    self.transformedname = pnmatch.group(1)
                pdepmatch = progDependencyMatch.match(z)
                if pdepmatch is not None:
                    self.dependencies.append(File(pdepmatch.group(1)))
                self.hash.update(z)
                self.length += 1
        self.hash = self.hash.hexdigest()

    def send(self, tc: telnetlib.Telnet):
        return None


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

    def addFile(self, file: File):
        fname = file.filename
        if fname in self.oldfiles.keys():
            if self.newfiles[fname].hash != file.hash:
                self.oldfiles[fname] = self.newfiles[fname]
                self.newfiles[fname] = file

    def syncOld(self, file: File, tc: telnetlib.Telnet):
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

