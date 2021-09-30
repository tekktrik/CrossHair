import random
import re
import sys
import unittest
from typing import *

import z3  # type: ignore

from crosshair.libimpl.builtinslib import SeqBasedSymbolicStr
from crosshair.libimpl.builtinslib import LazyIntSymbolicStr
from crosshair.libimpl.relib import _match_pattern
from crosshair.libimpl.relib import ReUnhandled

from crosshair.core_and_libs import *
from crosshair.core import deep_realize
from crosshair.options import AnalysisOptionSet
from crosshair.test_util import check_ok
from crosshair.test_util import check_fail
from crosshair.test_util import check_unknown
from crosshair.util import set_debug


def eval_regex(re_string, flags, test_string, offset, endpos=None):
    py_patt = re.compile(re_string, flags)
    with standalone_statespace as space:
        with NoTracing():
            s = LazyIntSymbolicStr([ord(c) for c in test_string])
            # "symstr" + space.uniq())
            # space.add(s.var == SeqBasedSymbolicStr._coerce_to_smt_sort(test_string))
            match = _match_pattern(py_patt, re_string, s, offset, endpos)
        return deep_realize(match)


class RegularExpressionUnitTests(unittest.TestCase):
    def test_handle_simple(self):
        self.assertIsNotNone(eval_regex("abc", 0, "abc", 0))
        self.assertIsNone(eval_regex("abc", 0, "ab", 0))

    def test_handle_or(self):
        self.assertIsNotNone(eval_regex("a|bc", 0, "bc", 0))
        self.assertEqual(eval_regex("a|bc", 0, "bc", 0).span(), (0, 2))

        self.assertIsNotNone(eval_regex("a|bc", 0, "ab", 0))
        self.assertEqual(eval_regex("a|bc", 0, "ab", 0).span(), (0, 1))

        self.assertIsNone(eval_regex("a|bc", 0, "c", 0))
        self.assertIsNone(eval_regex("a|bc", 0, "bd", 0))

    def test_handle_start_markers(self):
        self.assertIsNotNone(eval_regex(r"^ab", 0, "abc", 0))
        self.assertIsNotNone(eval_regex(r"\Aab", 0, "abc", 0))
        with self.assertRaises(ReUnhandled):
            # Surprisingly!: re.compile('^bc').match('abc', 1) is None
            # Even more surprisingly, the end markers work differently.
            # We simply don't handle start markers with offset:
            self.assertIsNone(eval_regex(r"^bc", 0, "abc", 1))

    def test_handle_end_markers(self):
        self.assertIsNotNone(eval_regex(r"abc$", 0, "abc", 0))
        self.assertIsNotNone(eval_regex(r"abc$", 0, "abcd", 0, 3))
        self.assertIsNotNone(eval_regex(r"abc\Z", 0, "abc", 0))
        self.assertIsNotNone(eval_regex(r"abc\Z", re.MULTILINE, "abc", 0))
        with self.assertRaises(ReUnhandled):
            self.assertIsNone(eval_regex("abc$", re.MULTILINE, "abc", 0))

    def test_handle_range(self):
        self.assertIsNotNone(eval_regex("[a-z]7", 0, "b7", 0))
        self.assertIsNotNone(eval_regex("[a-z]7", 0, "z7", 0))
        self.assertIsNone(eval_regex("[a-z]7", 0, "A7", 0))

    def test_handle_ascii_wildcard(self):
        self.assertIsNotNone(eval_regex("1.2", re.A, "1x2", 0))
        self.assertIsNotNone(eval_regex("1.2", re.A, "1\x002", 0))
        self.assertIsNone(eval_regex("1.2", re.A, "111", 0))

    def test_handle_repeats(self):
        self.assertIsNotNone(eval_regex("a+a", 0, "aa", 0))
        self.assertEqual(eval_regex("s", 0, "ssss", 0).span(), (0, 1))
        self.assertEqual(eval_regex("ss", 0, "ssss", 0).span(), (0, 2))
        self.assertIsNotNone(eval_regex("s{1,2}x", 0, "sx", 0))
        self.assertIsNotNone(eval_regex("s{1,2}x", 0, "ssx", 0))
        self.assertIsNone(eval_regex("s{1,2}x", 0, "sssx", 0))
        self.assertIsNone(eval_regex("s{1,2}x", 0, "x", 0))
        self.assertIsNotNone(eval_regex("s{2,3}", 0, "ssss", 0))
        self.assertEqual(eval_regex("s{2,3}", 0, "ssss", 0).span(), (0, 3))
        self.assertIsNotNone(eval_regex("y*", 0, "y", 0))
        self.assertEqual(eval_regex("y*", 0, "y", 0).span(), (0, 1))
        self.assertIsNotNone(eval_regex("y*e+", 0, "ye", 0))
        self.assertIsNotNone(eval_regex("y*e", 0, "yye", 0))
        self.assertEqual(eval_regex("y*e", 0, "yye", 0).span(), (0, 3))
        self.assertIsNotNone(eval_regex("y*e+s{2,3}x", 0, "yessx", 0))
        self.assertIsNotNone(eval_regex("y*e+s{2,3}x", 0, "essx", 0))
        self.assertIsNone(eval_regex("y*e+s{2,3}x", 0, "yyessssx", 0))
        self.assertIsNone(eval_regex("y*e+s{2,3}x", 0, "yssx", 0))
        self.assertIsNone(eval_regex("y*e+s{2,3}x", 0, "ex", 0))

    def test_handle_ascii_numeric(self):
        self.assertIsNotNone(eval_regex(r"a\d", re.A, "a3", 0))
        self.assertIsNotNone(eval_regex(r"a\d", re.A, "a0", 0))
        self.assertIsNone(eval_regex(r"a\d", re.A, "a-", 0))

    def test_handle_ascii_whitespace(self):
        self.assertIsNotNone(eval_regex(r"a\s", re.A, "a ", 0))
        self.assertIsNotNone(eval_regex(r"a\s", re.A, "a\r", 0))
        self.assertIsNone(eval_regex(r"a\s", re.A, "a.", 0))

    def test_handle_noncapturing_group(self):
        self.assertIsNotNone(eval_regex("(?:a|b)c", 0, "ac", 0))
        self.assertIsNotNone(eval_regex("(?:a|b)c", 0, "bc", 0))
        self.assertIsNone(eval_regex("(?:a|b)c", 0, "a", 0))

    def test_handle_capturing_group(self):
        self.assertIsNotNone(eval_regex("(a|b)c", 0, "ac", 0))
        self.assertIsNone(eval_regex("(a|b)c", 0, "a", 0))
        self.assertEqual(type(eval_regex("(a|b)c", 0, "bc", 0).groups()[0]), str)
        self.assertEqual(eval_regex("(a|b)c", 0, "bc", 0).groups(), ("b",))

    def test_handle_named_groups(self):
        self.assertIsNotNone(eval_regex("(?P<foo>a|b)c", 0, "bc", 0))
        self.assertEqual(eval_regex("(?P<foo>a|b)c", 0, "bc", 0)["foo"], "b")

    def test_handle_optional_named_groups(self):
        self.assertIsNone(eval_regex("a(?P<foo>b)?", 0, "a", 0)["foo"])
        self.assertIsNone(eval_regex("a(?P<foo>b)?c", 0, "ac", 0)["foo"])

    def test_handle_nested_groups(self):
        self.assertIsNotNone(eval_regex("(a|b(xx))+(c)?", 0, "bxxc", 0))
        self.assertEqual(eval_regex("(bxx)(c)?", 0, "bxxc", 0).groups(), ("bxx", "c"))
        self.assertEqual(
            eval_regex("(a|b(xx))+(c)?", 0, "bxxc", 0).groups(), ("bxx", "xx", "c")
        )
        self.assertEqual(
            eval_regex("(a|b(xx))+(c)?", 0, "a", 0).groups(), ("a", None, None)
        )

    def test_with_fuzzed_inputs(self) -> None:
        rand = random.Random(253209)

        def check(pattern, literal_string, offset):
            flags = re.ASCII | re.DOTALL
            sym_match = eval_regex(pattern, flags, literal_string, offset)
            py_match = re.compile(pattern, flags).match(literal_string, offset)
            if (sym_match is None) != (py_match is None):
                self.assertEqual(py_match, sym_match)
            if py_match is None:
                return
            self.assertEqual(py_match.span(), sym_match.span())
            self.assertEqual(py_match.group(0), sym_match.group(0))
            self.assertEqual(py_match.groups(), sym_match.groups())
            self.assertEqual(py_match.pos, sym_match.pos)
            self.assertEqual(py_match.endpos, sym_match.endpos)
            self.assertEqual(py_match.lastgroup, sym_match.lastgroup)

        for iter in range(100):
            literal_string = "".join(
                rand.choice(["a", "5", "_"])
                for _ in range(rand.choice([0, 1, 1, 2, 2, 3, 4]))
            )
            pattern = "".join(
                rand.choice(["a", "5", "."]) + rand.choice(["", "", "+", "*"])
                for _ in range(rand.choice([0, 1, 1, 2, 2]))
            )
            offset = rand.choice([0, 0, 0, 0, 1])
            with self.subTest(
                msg=f'Trial {iter}: evaluating pattern "{pattern}" against "{literal_string}" at {offset}'
            ):
                check(pattern, literal_string, offset)


class RegularExpressionTests(unittest.TestCase):
    def test_fullmatch_basic_fail(self) -> None:
        def f(s: str) -> Optional[re.Match]:
            """ post: _ """
            return re.compile("a").fullmatch(s)

        self.assertEqual(*check_fail(f))

    def test_star_fail(self) -> None:
        def f(s: str) -> bool:
            """
            pre: s[1] == 'a'
            post: _
            """
            return not re.fullmatch("a*", s)

        self.assertEqual(*check_fail(f))

    def test_plus_unknown(self) -> None:
        def f(s: str) -> bool:
            """
            pre: len(s) > 0
            post: _
            """
            return bool(re.fullmatch(".+", s, re.DOTALL))

        self.assertEqual(*check_unknown(f))

    def test_greedy_backtracking(self) -> None:
        def f(s: str) -> int:
            """
            pre: len(s) == 3
            post: _ == 3
            """
            return re.match(".+.", s, re.A | re.DOTALL).end()  # type: ignore

        self.assertEqual(*check_ok(f))

    def test_fullmatch_basic_ok(self) -> None:
        def f(s: str) -> Optional[re.Match]:
            """
            pre: s == 'a'
            post: _
            """
            return re.compile("a").fullmatch(s)

        self.assertEqual(*check_ok(f))

    def test_fullmatch_matches_whole_string(self) -> None:
        def f(s: str) -> Optional[re.Match]:
            """
            pre: len(s) == 3
            post: implies(_, s[-1] == 'b')
            """
            return re.compile("a+b+").fullmatch(s)

        self.assertEqual(*check_ok(f))

    def test_fullmatch_complex_fail(self) -> None:
        def f(s: str) -> str:
            """
            pre: re.fullmatch('a+Xb', s)
            post: _ != 'X'
            """
            return s[2]

        self.assertEqual(*check_fail(f))

    def test_match_basic_fail1(self) -> None:
        def f(s: str) -> bool:
            """
            pre: len(s) == 1
            post: _
            """
            return not re.compile("[a-z]").match(s)

        self.assertEqual(*check_fail(f))

    def test_match_basic_fail2(self) -> None:
        def f(s: str) -> bool:
            """ post: implies(_, len(s) <= 3) """
            return bool(re.compile("ab?c").match(s))

        self.assertEqual(*check_fail(f))

    def test_match_properties(self) -> None:
        test_string = "01ab9"
        match = re.compile("ab").match("01ab9", 2, 4)

        # Before we begin, quickly double-check that our expectations match what Python
        # actually does:
        assert match is not None
        self.assertEqual(match.span(), (2, 4))
        self.assertEqual(match.groups(), ())
        self.assertEqual(match.group(0), "ab")
        self.assertEqual(match[0], "ab")
        self.assertEqual(match.pos, 2)
        self.assertEqual(match.endpos, 4)
        self.assertEqual(match.lastgroup, None)
        self.assertEqual(match.string, "01ab9")
        self.assertEqual(match.re.pattern, "ab")

        def f(s: str) -> Optional[re.Match]:
            """
            pre: s == '01ab9'
            post: _.span() == (2, 4)
            post: _.groups() == ()
            post: _.group(0) == 'ab'
            post: _[0] == 'ab'
            post: _.pos == 2
            post: _.endpos == 4
            post: _.lastgroup == None
            post: _.string == '01ab9'
            post: _.re.pattern == 'ab'
            """
            return re.compile("ab").match(s, 2, 4)

        self.assertEqual(*check_ok(f))

    def test_number_parse(self) -> None:
        number_re = re.compile(r"(-?(?:0|[1-9]\d*))(\.\d+)?([eE][-+]?\d+)?")

        def f(s: str):
            """
            pre: len(s) == 4
            post: not _
            """
            return bool(number_re.fullmatch(s))

        self.assertEqual(
            *check_fail(
                f,
                AnalysisOptionSet(
                    max_iterations=20, per_path_timeout=5, per_condition_timeout=20
                ),
            )
        )


if __name__ == "__main__":
    if ("-v" in sys.argv) or ("--verbose" in sys.argv):
        set_debug(True)
    unittest.main()
