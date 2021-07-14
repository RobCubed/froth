import froth

BASICS = """
1 1 1
1 2 add
3 2 sub
"""
vm = froth.VM(BASICS)

assert vm.runUntilEnd() == froth.Errors.END_OF_PROGRAM
assert vm.stack == [1, 1, 1, 3, 1]

print("PASSED BASIC TESTS")

MACRO = """
macro two 1 1 add ; 1
two

macro inc 1 add ;
macro dec 1 sub ;

5 var loopbegin
line var line_position
loopbegin dup
dec dup var loopbegin 0 eq not if line_position jump ;

"""

vm = froth.VM(MACRO)
end = vm.runUntilEnd()
assert end == froth.Errors.END_OF_PROGRAM
assert vm.stack == [1, 2, 5, 4, 3, 2, 1]

print("PASSED MACRO TESTS")

JUMP = """
3 jump
1234
67
2 reljump
89

"""

vm = froth.VM(JUMP)
assert vm.runUntilEnd() == froth.Errors.END_OF_PROGRAM
assert vm.stack == [67]

print("PASSED JUMP TESTS")


IF = """
0 if 58 ; 2
1 if 2 reljump ; 5
6
"""

vm = froth.VM(IF)
end = vm.runUntilEnd()
assert end == froth.Errors.END_OF_PROGRAM
assert vm.stack == [2]

print("PASSED IF TESTS")

MEMORY = """
10 alloc
5 85 memwrite
5 memread
here
5 dealloc
here
"""

vm = froth.VM(MEMORY)
end = vm.runUntilEnd()
assert end == froth.Errors.END_OF_PROGRAM
assert vm.stack == [85, 10, 5]

print("PASSED MEMORY TESTS")


COMMENTS = """
1 ( 2 )
( 3
5 )
"""

vm = froth.VM(COMMENTS)
end = vm.runUntilEnd()
assert end == froth.Errors.END_OF_PROGRAM
assert vm.stack == [1, 5]

print("PASSED COMMENT TESTS")


NESTED = """
macro test if 1 2 3 4 ; ;
1 test
0 test
"""
vm = froth.VM(NESTED)
end = vm.runUntilEnd()
assert end == froth.Errors.END_OF_PROGRAM
assert vm.stack == [1, 2, 3, 4]

print("PASSED NESTED TESTS")

def CustomWord(vm: froth.VM):
    vm.stack.append(50)

CUSTOM = """
custom
"""
vm = froth.VM(CUSTOM, customWords={"custom": (CustomWord, 0)})
end = vm.runUntilEnd()
assert end == froth.Errors.END_OF_PROGRAM
assert vm.stack == [50]
vm = froth.VM(CUSTOM)
end = vm.runUntilEnd()
assert end == froth.Errors.UNKNOWN_WORD

print("PASSED CUSTOM TOKEN TESTS")


STRINGS = """
"Hello World!"
"""
vm = froth.VM(STRINGS)
end = vm.runUntilEnd()
assert end == froth.Errors.END_OF_PROGRAM
assert vm.stack == [33, 100, 108, 114, 111, 87, 32, 111, 108, 108, 101, 72, 12]

print("PASSED STRING TESTS")

CATCH = """
line 2 add var handler
2 reljump
1 2 3 4 jumpto jump


line 3 add var jumpto
UNKNOWN_WORD handler catch 
idiot
UNKNOWN_WORD endcatch

UNKNOWN_WORD -1 catch 
43 idiot
UNKNOWN_WORD endcatch

MEMORY_ERROR -1 catch 
MEMORY_ERROR endcatch 

99 memread

"""
vm = froth.VM(CATCH)
end = vm.runUntilEnd()
assert end == froth.Errors.MEMORY_ERROR
assert vm.stack == [1, 2, 3, 4, 43]

print("PASSED CATCH TESTS")


RAISE = """

34 -1 catch
34 raise
34 endcatch

35 raise


"""
vm = froth.VM(RAISE)
end = vm.runUntilEnd()
assert end.name == "USER_ERROR_35"
assert vm.stack == []

print("PASSES RAISE TESTS")

DEMO = """
( macro that subtracts one from the top of the stack )
macro dec ( a -- a-1 ) 1 sub ;

( We will count down from this value )
20 var loopbegin

( load the position of one line below this into the variable "line_position" )
line 1 add var line_position
( load the current value into stack for demostration )
loopbegin
( draw a neat line )
50 loopbegin mul ( 5 * current loop iter > x1 )
10 ( y1 ) 
loopbegin loopbegin mul  ( iter * iter > x2 )
loopbegin 20 mul 2 div  ( iter / 2 > y2 )
drawline ( draw, adds the id onto the stack )
( loads our current position onto the stack, subtracts one from it, overwrite the old variable, check if it is equal to zero, )
( and if not, jump to the beginning of the loop )
loopbegin dec dup var loopbegin 0 eq  not if line_position jump ;
"""