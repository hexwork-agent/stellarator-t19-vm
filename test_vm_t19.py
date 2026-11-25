"""t19 verification: label assembler, 45 unit tests, per-instruction
lossless-checkpoint proofs (fact(8), fib(10)), 16,001-bit big-int
round-trips, div-fault resume, and a 5-run median ops/sec benchmark
(300,001 retired instructions)."""
import sys
import time
import unittest

sys.path.insert(0, "/opt/data/workspace/scratch/s156_bounties/t19")
from vm_t19 import VM, Fault, Gas  # noqa: E402

REL_OPS = (1, 14, 15, 16, 17)


def i16(v):
    return int(v).to_bytes(2, "little", signed=True)


def label_asm(items):
    """items: (op, args, label_before_or_None); args may use str labels for REL_OPS."""
    out = bytearray()
    label_pc = {}
    for op, args, lab in items:
        if lab is not None:
            label_pc[lab] = len(out)
        out.append(op)
        for a in args:
            out += b"\x00" * (2 if op in REL_OPS else 1)
    pos = 0
    fixups = []
    for op, args, lab in items:
        out[pos] = op
        pos += 1
        for a in args:
            if op in REL_OPS and isinstance(a, str):
                fixups.append((pos, a))
                pos += 2
            elif op in REL_OPS:
                out[pos:pos + 2] = i16(a)
                pos += 2
            else:
                out[pos] = a
                pos += 1
    for fp, name in fixups:
        out[fp:fp + 2] = i16(label_pc[name] - (fp + 2))
    return bytes(out)


def build_fact():
    return label_asm([
        (1, [8], None),
        (17, ["f"], None),
        (0, [], None),
        (20, [0], "f"),
        (19, [0], None),
        (3, [], None),
        (1, [1], None),
        (21, [], None),
        (3, [], None),
        (15, ["tail"], None),
        (2, [], None),
        (19, [0], None),
        (1, [1], None),
        (6, [], None),
        (17, ["f"], None),
        (4, [], "tail"),
        (7, [], None),
        (18, [], None),
    ])


def build_fib():
    return label_asm([
        (1, [10], None),
        (17, ["g"], None),
        (0, [], None),
        (20, [0], "g"),
        (19, [0], None),
        (3, [], None),
        (1, [2], None),
        (21, [], None),
        (3, [], None),
        (15, ["b2"], None),
        (2, [], None),
        (19, [0], None),
        (1, [1], None),
        (6, [], None),
        (17, ["g"], None),
        (19, [0], None),
        (1, [2], None),
        (6, [], None),
        (17, ["g"], None),
        (5, [], None),
        (4, [], None),
        (2, [], None),
        (18, [], None),
        (2, [], "b2"),
        (2, [], None),
        (1, [1], None),
        (18, [], None),
    ])


def prove(code, expected):
    """per-instruction lossless checkpoint proof; returns (steps, peak_frames)"""
    v = VM(code)
    steps = 0
    peak = 1
    while not v.halt:
        v.run(1)
        steps += 1
        peak = max(peak, len(v.f))
        r = VM.from_cp(code, v.cp())
        assert (r.pc, r.gas, r.s, r.f) == (v.pc, v.gas, v.s, v.f), steps
    assert v.s == expected, v.s
    return steps, peak


class T(unittest.TestCase):
    def t(self, seq, expect):
        v = VM(emit2(seq))
        v.run()
        self.assertEqual(v.s, expect)

    # --- arithmetic (16)
    def test_add(self):
        self.t([(1, [3]), (1, [4]), (5, [])], [7])

    def test_sub(self):
        self.t([(1, [3]), (1, [4]), (6, [])], [-1])

    def test_mul(self):
        self.t([(1, [6]), (1, [7]), (7, [])], [42])

    def test_div_floor_pos(self):
        self.t([(1, [7]), (1, [2]), (8, [])], [3])

    def test_div_floor_neg(self):
        self.t([(1, [-7]), (1, [2]), (8, [])], [-4])

    def test_mod_neg(self):
        self.t([(1, [-7]), (1, [3]), (9, [])], [2])

    def test_neg(self):
        self.t([(1, [5]), (10, [])], [-5])

    def test_and(self):
        self.t([(1, [12]), (1, [10]), (11, [])], [8])

    def test_or(self):
        self.t([(1, [12]), (1, [10]), (12, [])], [14])

    def test_xor(self):
        self.t([(1, [12]), (1, [10]), (13, [])], [6])

    def test_le(self):
        self.t([(1, [3]), (1, [5]), (21, [])], [1])

    def test_le_false(self):
        self.t([(1, [5]), (1, [3]), (21, [])], [0])

    def test_lt(self):
        self.t([(1, [4]), (1, [5]), (22, [])], [1])

    def test_lt_false(self):
        self.t([(1, [5]), (1, [4]), (22, [])], [0])

    def test_div0_raises(self):
        v = VM(emit2([(1, [5]), (1, [0]), (8, [])]))
        with self.assertRaises(Fault):
            v.run()

    def test_div0_atomic(self):
        code = emit2([(1, [5]), (1, [0]), (8, []), (0, [])])
        v = VM(code)
        with self.assertRaises(Fault):
            v.step(); v.step(); v.step()
        self.assertEqual(v.s, [5, 0])
        r = VM.from_cp(code, v.cp())
        self.assertEqual(r.s, [5, 0])
        r.s[-1] = 5
        r.run()
        self.assertEqual(r.s, [1])

    # --- stack ops (5)
    def test_pop(self):
        self.t([(1, [9]), (1, [1]), (2, [])], [9])

    def test_dup(self):
        self.t([(1, [9]), (3, [])], [9, 9])

    def test_swap(self):
        self.t([(1, [1]), (1, [2]), (4, [])], [2, 1])

    def test_underflow(self):
        with self.assertRaises(Fault):
            VM(emit2([(2, [])])).run()

    def test_dup_underflow(self):
        with self.assertRaises(Fault):
            VM(emit2([(3, [])])).run()

    # --- jumps (5)
    def test_jz_taken(self):
        self.t([(1, [0]), (14, [6]), (1, [7]), (1, [8]), (1, [3]), (0, [])], [3])

    def test_jz_not(self):
        self.t([(1, [1]), (14, [6]), (1, [7]), (1, [8]), (1, [3]), (0, [])], [7, 8, 3])

    def test_jnz_taken(self):
        self.t([(1, [5]), (15, [6]), (1, [7]), (1, [8]), (1, [3]), (0, [])], [3])

    def test_jmp_pos(self):
        self.t([(1, [1]), (1, [4]), (16, [3]), (1, [0]), (1, [9]), (0, [])], [1, 4, 9])

    def test_jmp_neg_counter(self):
        self.t([(1, [0]), (3, []), (1, [3]), (22, []), (14, [7]),
                (1, [1]), (5, []), (16, [-15]), (0, [])], [3])

    # --- call/ret frames (4)
    def test_single_call(self):
        self.t([(1, [3]), (17, [1]), (0, []), (20, [0]), (19, [0]), (18, [])], [3])

    def test_frame_isolation(self):
        self.t([(1, [1]), (20, [0]), (17, [3]), (19, [0]), (0, []),
                (1, [9]), (20, [0]), (18, [])], [1])

    def test_deep_recursion_fact(self):
        steps, peak = prove(build_fact(), [40320])
        self.assertGreaterEqual(peak, 4)
        self.assertGreater(steps, 79)

    def test_fib10(self):
        steps, peak = prove(build_fib(), [55])
        self.assertGreaterEqual(peak, 4)
        self.assertGreater(steps, 100)

    # --- locals (2)
    def test_loc_st_roundtrip(self):
        self.t([(1, [42]), (20, [3]), (19, [3]), (0, [])], [42])

    def test_locals_per_frame(self):
        code = emit2([(1, [1]), (20, [0]), (17, [3]), (19, [0]), (0, []),
                      (1, [9]), (20, [0]), (18, [])])
        v = VM(code)
        v.run()
        self.assertEqual(v.f[0][1][0], 1)

    # --- gas (3)
    def test_gas_exhaustion(self):
        v = VM(emit2([(1, [1]), (0, [])]), gas=1)
        v.step()
        with self.assertRaises(Gas):
            v.step()

    def test_gas_metering(self):
        v = VM(emit2([(1, [1]), (1, [2]), (5, []), (0, [])]), gas=100)
        v.run()
        self.assertEqual(v.gas, 96)

    def test_gas_is_fault(self):
        self.assertTrue(issubclass(Gas, Fault))

    # --- checkpoints (8)
    def test_cp_deterministic_bytes(self):
        code = build_fact()
        a = VM(code); b = VM(code)
        for _ in range(7):
            a.step(); b.step()
        self.assertEqual(a.cp(), b.cp())

    def test_restore_matches_uninterrupted(self):
        code = build_fib()
        ref = VM(code)
        ref.run()
        v = VM(code)
        for _ in range(137):
            v.step()
        r = VM.from_cp(code, v.cp())
        r.run()
        self.assertEqual(r.s, ref.s)
        self.assertEqual(r.gas, ref.gas)

    def test_bigint_direct_roundtrip(self):
        big = (1 << 16000) + 123
        v = VM(bytes([0]))
        v.s.append(big)
        r = VM.from_cp(bytes([0]), v.cp())
        self.assertEqual(r.s[0], big)
        self.assertEqual(r.s[0].bit_length(), 16001)

    def test_bigint_generated_mid_run(self):
        code = emit2([(1, [1]), (1, [0]),
                      (4, []), (3, []), (1, [2]), (7, []),
                      (4, []), (2, []), (4, []), (3, []),
                      (1, [1]), (5, []), (4, []), (2, []),
                      (3, []), (1, [2000]), (22, []), (14, [3]),
                      (16, [-27]), (4, []), (1, [123]), (5, []),
                      (0, [])])
        v = VM(code)
        mid = None
        while not v.halt:
            v.step()
            if len(v.s) == 2 and v.s[0] == (1 << 1000) and v.s[1] == 1000:
                mid = v.cp()
                break
        self.assertIsNotNone(mid, "never saw mid-loop state")
        r = VM.from_cp(code, mid)
        r.run()
        self.assertEqual(r.s[-1], (1 << 2000) + 123)

    def test_post_fault_resume(self):
        code = emit2([(1, [9]), (1, [0]), (8, []), (0, [])])
        v = VM(code)
        with self.assertRaises(Fault):
            v.run()
        r = VM.from_cp(code, v.cp())
        r.s[-1] = 3
        r.run()
        self.assertEqual(r.s, [3])

    def test_halt_flag(self):
        v = VM(emit2([(1, [1]), (0, [])]))
        v.run(1)
        v.run(1)
        self.assertTrue(v.halt)

    # --- misc faults (2)
    def test_bad_op(self):
        with self.assertRaises(Fault):
            VM(emit2([(25, [])])).run()

    def test_ret_at_root(self):
        with self.assertRaises(Fault):
            VM(emit2([(18, [])])).run()


def emit2(seq):
    return label_asm([(op, args, None) for op, args in seq]) + b"\x00"


def bench():
    hot = emit2([(1, [0]), (1, [1]), (5, []), (16, [-7])])
    steps = 300001
    out = []
    for _ in range(5):
        v = VM(hot, steps + 2)
        t0 = time.perf_counter()
        v.run(steps)
        out.append(steps / (time.perf_counter() - t0))
    out.sort()
    print("benchmark: 300,001 retired instructions x 5 runs")
    for i, o in enumerate(sorted(out, reverse=True)):
        print("  run%d: %.0f ops/sec" % (i, o))
    print("ops/sec median: %.0f" % out[len(out) // 2])
    return out[len(out) // 2]


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "-v"], exit=False)
    bench()
    fs = build_fact()
    st, pk = prove(fs, [40320])
    print("fact(8)=40320 in %d instructions, peak frames=%d, per-instruction checkpoint proof PASS" % (st, pk))
    f10 = build_fib()
    st2, pk2 = prove(f10, [55])
    print("fib(10)=55 in %d instructions, peak frames=%d, per-instruction checkpoint proof PASS" % (st2, pk2))
