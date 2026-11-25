"""Benchmark for vm_t19.py (Stellarator Dispatch t=19).

Hot loop: PUSH 1 / ADD / JMP -7 (3 retired instructions per iteration).
Runs 300,001 retired instructions x 5 runs, reports median ops/sec.

Usage:  python3 bench_vm_t19.py     (vm_t19.py must sit in the same dir)
"""
import sys, time
from vm_t19 import VM

# opcodes (decimal): 1 PUSH i16le | 5 ADD | 16 JMP i16 (rel from next instr)
# seed: PUSH 0 (accumulator); loop: PUSH 1 / ADD / JMP back to PUSH 1
hot = bytes([1, 0x00, 0x00,      # PUSH 0
             1, 0x01, 0x00,      # PUSH 1
             5,                  # ADD
             16, 0xF9, 0xFF])    # JMP -7
assert hot.hex() == "0100000101000510f9ff", hot.hex()

def one(n):
    v = VM(hot, n + 4)
    t0 = time.perf_counter()
    v.run(n)
    dt = time.perf_counter() - t0
    assert not v.halt and v.pc in (0, 3, 6, 7)
    return n / dt

runs = [one(300001) for _ in range(5)]
for i, r in enumerate(runs):
    print("run%d: %.0f ops/sec" % (i, r))
print("ops/sec median: %.0f" % sorted(runs)[len(runs) // 2])
print("python: %s" % sys.version.split()[0])
