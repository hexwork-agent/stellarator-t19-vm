"""T19: <=4KB stack VM, pure Python 3.12 stdlib.
ISA (decimal): 0 HLT|1 PUSH i16le|2 POP|3 DUP|4 SWAP|5 ADD|6 SUB|7 MUL|8 DIV(floor)|9 MOD|10 NEG|11 AND|12 OR|13 XOR|14 JZ i16|15 JNZ i16|16 JMP i16|17 CALL i16|18 RET (rel from next instr)|19 LOCLI u8|20 STCLI u8 (per-frame locals[8])|21 LE|22 LT (a<=b/a<b -> 1/0).
Gas: 1 unit per retired instruction, checked before, metered after; faults (underflow/div0/bad op/ret@root/out of range/Gas) atomic - operands read/validated before mutation.
cp() -> deterministic JSON bytes [pc, gas, stack, frames]; frames=[ret|None, locals[8]]; from_cp() restores exact state, big ints included."""
import json, sys
try: sys.set_int_max_str_digits(10**6)
except (AttributeError, ValueError): pass


class Fault(Exception): pass


class Gas(Fault): pass


U, D, B, R, O = Fault("underflow"), Fault("div0"), Fault("bad op"), Fault("ret at root"), Fault("out of range")


def I(c, p):
    v = c[p] | c[p + 1] << 8
    return v - 65536 if v & 32768 else v


class VM:
    def __init__(self, c, gas=1 << 30):
        self.c, self.gas, self.pc, self.s, self.f, self.halt = c, gas, 0, [], [[None, [0] * 8]], False

    def cp(self):
        return json.dumps([self.pc, self.gas, self.s, self.f]).encode()

    @classmethod
    def from_cp(cls, c, d):
        v = cls(c, 0)
        v.pc, v.gas, v.s, v.f = json.loads(d)
        return v

    def run(self, n=None):
        if n is None:
            while self.step(): pass
        else:
            while n and self.step():
                n -= 1

    def step(self):
        g = self.gas
        if g < 1: raise Gas
        self.gas = g - 1
        c, s, f = self.c, self.s, self.f
        try:
            pc = a1 = self.pc + 1
            op = c[a1 - 1]
            if op == 1:
                s.append(I(c, a1)); pc = a1 + 2
            elif op == 5:
                if len(s) < 2: raise U
                b = s.pop(); s[-1] += b
            elif op == 16:
                pc = a1 + 2 + I(c, a1)
            elif op == 0:
                self.halt = 1
            elif op == 2:
                if not s: raise U
                s.pop()
            elif op == 3:
                if not s: raise U
                s.append(s[-1])
            elif op == 4:
                if len(s) < 2: raise U
                s[-1], s[-2] = s[-2], s[-1]
            elif op == 6:
                if len(s) < 2: raise U
                b = s.pop(); s[-1] -= b
            elif op == 7:
                if len(s) < 2: raise U
                b = s.pop(); s[-1] *= b
            elif op in (8, 9):
                if len(s) < 2: raise U
                if s[-1] == 0: raise D
                b = s.pop(); s[-1] = s[-1] // b if op == 8 else s[-1] % b
            elif op == 10:
                if not s: raise U
                s[-1] = -s[-1]
            elif op in (11, 12, 13):
                if len(s) < 2: raise U
                b = s.pop(); s[-1] = s[-1] ^ b if op == 13 else s[-1] | b if op == 12 else s[-1] & b
            elif op in (14, 15):
                if not s: raise U
                w = s.pop()
                pc = a1 + 2
                if (w == 0) == (op == 14): pc += I(c, a1)
            elif op == 17:
                f.append([a1 + 2, [0] * 8]); pc = a1 + 2 + I(c, a1)
            elif op == 18:
                if len(f) <= 1: raise R
                pc = f.pop()[0]
            elif op == 19:
                s.append(f[-1][1][c[a1]]); pc = a1 + 1
            elif op == 20:
                if not s: raise U
                f[-1][1][c[a1]] = s.pop(); pc = a1 + 1
            elif op in (21, 22):
                if len(s) < 2: raise U
                b = s.pop(); a = s.pop()
                s.append(1 if a < b else 1 if a == b and op == 21 else 0)
            else:
                raise B
        except IndexError:
            raise O
        self.pc = pc
        return not self.halt
