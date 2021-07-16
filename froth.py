import sys
import random
import enum
from io import StringIO

class Errors(enum.IntEnum):
    UNDEFINED = 0
    SUCCESS = 1
    STACK_UNDERFLOW = 2
    END_OF_PROGRAM = 3
    END_OF_LINE = 4
    UNKNOWN_WORD = 5
    MEMORY_ERROR = 6
    DEPTH_EXCEEDED = 7
    DIVIDE_BY_ZERO = 8

def isDigit(v):
    try:
        int(v)
        return True
    except:
        return False

def MakeToken(data):
    if isDigit(data):
        return int(data)
    return data

class FakeEnumValue(object):
    def __init__(self, name, value):
        self.name = name
        self.value = value


tokenMap = {}
flowWords = []

def flowWord(func):
    flowWords.append(func.__name__.strip("_"))
    return func

def token(func):
    tokenMap[func.__name__] = (func, 0)
    return func


def argToken(num, name=None):
    def _(func):
        # try to do this rationally
        # pro-tip: you cant
        if not name:
            nam = func.__name__
        else: nam = name
        tokenMap[nam] = (func, num)
        return func
    return _

class VM(object):
    def __init__(self, code, output=sys.stdout, customWords={}):
        self.stack = []
        self.tokens = tokenMap.copy()
        self.tokens.update(customWords)

        self.variables = {err.name:int(err) for err in Errors}
        self.memory = []
        self.catchMap = {}
        self.output = output
        self.code = code.split("\n")
        self.pc = -1

        self.curline = None

    def readFlow(self):
        sequence = []
        depth = 0
        while (word := self.curline.pop(0)) != None:
            if word in flowWords:
                depth += 1
            if word == ";":
                if depth <= 0: break
                depth -= 1
            sequence.append(word)
        return sequence


    def runUntilEnd(self):
        while (thing := self.tick()) == Errors.SUCCESS:
            pass
        return thing

    def tokenizer(self, string):
        ret = []
        buf = ""
        comment = False
        isString = False
        escape = False
        if isinstance(string, str): string = StringIO(string)
        while char := string.read(1):
            if escape and not comment:
                buf += char
                escape = False
            elif char == "\\":
                escape = True
            elif char == " " and (not comment and not isString):
                if buf:
                    ret.append(MakeToken(buf))
                buf = ""
            elif char == "(" and not isString:
                if buf:
                    ret.append(MakeToken(buf))
                buf = ""
                comment = True
            elif char == ")":
                comment = False
                buf = ""
            elif char == '"':
                if comment: continue
                if buf and not isString:
                    ret.append(MakeToken(buf))
                elif isString:
                    l = len(buf)
                    ret += reversed([ord(x) for x in buf])
                    ret.append(l)
                buf = ""
                isString = not isString
            elif not comment:
                buf += char
        if buf and not comment: ret.append(MakeToken(buf))
        if isString: return Errors.END_OF_LINE
        return ret




    def tick(self):
        try:
            line = self.code[self.pc].rstrip().strip()
        except:
            return Errors.END_OF_PROGRAM

        if line.startswith("#") or len(line) == 0:
            self.pc += 1
            return Errors.SUCCESS

        self.curline = self.tokenizer(line)
        if not isinstance(self.curline, list):
            return self.curline

        ret = self.exec()
        if ret.value in self.catchMap:
            if self.catchMap[ret.value] >= 0:
                self.pc = self.catchMap[ret.value]
            else: self.pc += 1
            return Errors.SUCCESS
        return ret


    def exec(self):
        try:
            while (word := self.curline.pop(0)) != None:

                if word in self.tokens:
                    args = []
                    try:
                        for _ in range(self.tokens[word][1]):
                            args.append(self.curline.pop(0))
                    except IndexError:
                        return Errors.END_OF_LINE

                    try:
                        ret = self.tokens[word][0](self, *args)
                    except IndexError:
                        return Errors.STACK_UNDERFLOW
                    if ret:
                        return ret
                elif word in self.variables:
                    if isinstance(self.variables[word], list):
                        self.curline = self.variables[word].copy() + self.curline
                    else:
                        self.stack.append(self.variables[word])
                elif isinstance(word, int):
                    self.stack.append(int(word))
                else:
                    return Errors.UNKNOWN_WORD

        except IndexError:
            self.pc += 1
            return Errors.SUCCESS


    @token
    def debug(self):
        self.output.write(f"[DEBUG] pc = {self.pc} | stack = {self.stack} | variables = {self.variables}\n")
        self.output.flush()

    # ------- Math --------
    @token
    def add(self):
        "( a b -- a+b )"
        self.stack.append(self.stack.pop() + self.stack.pop())

    @token
    def sub(self):
        "( a b -- a-b )"
        self.stack.append(self.stack.pop(-2) - self.stack.pop())

    @token
    def mul(self):
        "( a b -- a*b )"
        self.stack.append(self.stack.pop() * self.stack.pop())

    @token
    def div(self):
        "( a b -- n/n )"
        try:
            self.stack.append(self.stack.pop(-2) // self.stack.pop())
        except ZeroDivisionError:
            return Errors.DIVIDE_BY_ZERO

    @token
    def mod(self):
        "( a b -- n%n )"
        self.stack.append(self.stack.pop() % self.stack.pop())

    @token
    def rand(self):
        "( n -- random(0->n) )"
        self.stack.append(random.randrange(0, self.stack.pop()))

    # ------- Bitwise ops --------
    @token
    def xor(self):
        "( a b -- a ^ b )"
        self.stack.append(self.stack.pop() ^ self.stack.pop())

    @token
    def lshift(self):
        "( a b -- a << b )"
        amount = self.stack.pop()
        bits = self.stack.pop()
        self.stack.append(bits << amount)

    @token
    def rshift(self):
        "( a b -- a >> b )"
        amount = self.stack.pop()
        bits = self.stack.pop()
        self.stack.append(bits >> amount)

    @argToken(0, name="and")
    def _and(self):
        "( a b -- a & b )"
        and1 = self.stack.pop()
        and2 = self.stack.pop()
        self.stack.append(and2 & and1)

    @argToken(0, name="or")
    def _or(self):
        "( a b -- a | b )"
        or1 = self.stack.pop()
        or2 = self.stack.pop()
        self.stack.append(or2 | or1)

    @argToken(0, name="not")
    def _not(self):
        "( a -- !a )"
        self.stack.append(~self.stack.pop())

    # ------- Stack ops --------
    @token
    def drop(self):
        "( a -- )"
        self.stack.pop()

    @token
    def swap(self):
        "( a b -- b a )"
        self.stack.append(self.stack.pop(-2))

    @token
    def dup(self):
        "( n -- n n )"
        self.stack.append(self.stack[-1])

    @token
    def over(self):
        "( a b -- a b a )"
        self.stack.append(self.stack[-2])

    @token
    def rot(self):
        "( a b c -- c a b )"
        self.stack.append(self.stack.pop(-3))
        self.stack.append(self.stack.pop(-3))

    # ------- Output --------
    @token
    def p(self):
        "( a -- )"
        self.output.write(str(self.stack.pop()))
        self.output.flush()

    @token
    def emit(self):
        "( a -- )"
        self.output.write(chr(self.stack.pop()))
        self.output.flush()

    @token
    def cr(self):
        "( -- )"
        self.output.write("\n")
        self.output.flush()

    # ------- Boolean ops --------
    @token
    def eq(self):
        "( a b -- a==b )"
        self.stack.append(-1 if self.stack.pop() == self.stack.pop() else 0)

    @token
    def lt(self):
        "( a b -- a<b )"
        self.stack.append(-1 if self.stack.pop() > self.stack.pop() else 0)

    @token
    def gt(self):
        "( a b -- a>b )"
        self.stack.append(-1 if self.stack.pop() < self.stack.pop() else 0)

    # ------- Control Flow --------
    @token
    def line(self):
        "( -- [current line] )"
        self.stack.append(self.pc)

    @token
    def jump(self):
        "( line -- )"
        self.pc = self.stack.pop()
        return Errors.SUCCESS

    @token
    def reljump(self):
        "( a -- )"
        pop = self.stack.pop()
        self.pc = self.pc + pop
        return Errors.SUCCESS

    @flowWord
    @argToken(0, name="if")
    def _if(self):
        try:
            sequence = self.readFlow()
        except IndexError:
            return Errors.END_OF_LINE
        if self.stack.pop():
            self.curline = sequence + self.curline

    @token
    def catch(self):
        "( errno line_handler -- )"
        handler = self.stack.pop()
        errno = self.stack.pop()
        self.catchMap[errno] = handler

    @token
    def endcatch(self):
        "( errno -- )"
        del self.catchMap[self.stack.pop()]

    @argToken(0, name="raise")
    def _raise(self):
        "(errno -- )"
        pop = self.stack.pop()
        return FakeEnumValue(f"USER_ERROR_{pop}", pop)


    # ------- Data storage --------
    @argToken(1)
    def var(self, name):
        "( var -- )"
        self.variables[name] = self.stack.pop()

    @token
    def alloc(self):
        "( size -- )"
        self.memory += [0 for _ in range(self.stack.pop())]

    @token
    def dealloc(self):
        "( size -- )"
        self.memory = self.memory[:self.stack.pop()*-1:]

    @token
    def memread(self):
        "( pos -- value )"
        pos = self.stack.pop()
        try:
            self.stack.append(self.memory[pos])
        except IndexError:
            return Errors.MEMORY_ERROR

    @token
    def memwrite(self):
        "( address data -- )"
        data = self.stack.pop()
        address = self.stack.pop()
        try:
            self.memory[address] = data
        except IndexError:
            return Errors.MEMORY_ERROR

    @token
    def here(self):
        "( -- [memory end position] )"
        self.stack.append(len(self.memory))

    # ------- Language building --------
    @flowWord
    @argToken(1)
    def macro(self, name):
        try:
            sequence = self.readFlow()
        except IndexError:
            return Errors.END_OF_LINE
        self.variables[name] = sequence
