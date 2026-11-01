"""Tests for eval/metrics.py (briefs/eval.md). Run from the repo root:
    python -m unittest tests.test_metrics -v
"""
import unittest

from eval.metrics import cer, normalize, wer, word_alignment


class NormalizeTest(unittest.TestCase):

    def test_case_and_sentence_marks(self):
        self.assertEqual(normalize("Բարև, ինչպե՞ս ես։"), "բարեւ ինչպես ես")

    def test_marks_on_a_word_are_removed_not_split(self):
        for text in ("ինչպե՞ս", "ինչպե՜ս", "ինչպե՛ս", "ինչպես"):
            self.assertEqual(normalize(text), "ինչպես")

    def test_full_stop_without_space_still_separates_words(self):
        self.assertEqual(normalize("տեսախցիկ։Ու արդեն"), "տեսախցիկ ու արդեն")
        self.assertEqual(normalize("ասաց.Ու"), "ասաց ու")

    def test_ascii_colon_and_other_punctuation(self):
        self.assertEqual(normalize("«Լավ»: Հա — ոչ… (իհարկե)!"), "լավ հա ոչ իհարկե")

    def test_yev_ligature(self):
        self.assertEqual(normalize("Երևան և"), normalize("Երեւան եւ"))
        self.assertEqual(normalize("Երևան"), "երեւան")

    def test_whitespace(self):
        self.assertEqual(normalize("  ժամը\tութ \n անց  "), "ժամը ութ անց")

    def test_digits_kept(self):
        self.assertEqual(normalize("33,34 րոպե"), "33 34 րոպե")

    def test_punctuation_only_is_empty(self):
        self.assertEqual(normalize("։ , ՞"), "")


class RatesTest(unittest.TestCase):

    def test_identical_after_normalisation_is_zero(self):
        self.assertEqual(wer(["Բարև, ինչպե՞ս ես։"], ["բարեւ ինչպես ես"]), 0.0)
        self.assertEqual(cer(["Բարև, ինչպե՞ս ես։"], ["բարեւ ինչպես ես"]), 0.0)

    def test_one_wrong_word_of_four(self):
        self.assertAlmostEqual(wer(["ես սիրում եմ կիթառ"], ["ես սիրում եմ կիտառ"]), 0.25)
        # one letter of 18 characters (spaces count)
        self.assertAlmostEqual(cer(["ես սիրում եմ կիթառ"], ["ես սիրում եմ կիտառ"]), 1 / 18)

    def test_deletion_and_insertion(self):
        self.assertAlmostEqual(wer(["ա բ գ դ"], ["ա գ դ"]), 0.25)
        self.assertAlmostEqual(wer(["ա բ"], ["ա բ գ դ"]), 1.0)     # 2 inserted / 2 reference words

    def test_corpus_level_not_average(self):
        # 1 error in 1 word + 0 errors in 9 words = 1 / 10, not the average of 100 % and 0 %
        self.assertAlmostEqual(wer(["ա", "բ գ դ ե զ է ը թ ժ"], ["բ", "բ գ դ ե զ է ը թ ժ"]), 0.1)

    def test_empty_hypothesis_is_all_deleted(self):
        self.assertEqual(wer(["ա բ"], [""]), 1.0)

    def test_bad_input_raises(self):
        with self.assertRaises(ValueError):
            wer(["ա"], ["ա", "բ"])
        with self.assertRaises(ValueError):
            wer([], [])
        with self.assertRaises(ValueError):
            cer(["։"], ["ա"])                 # empty reference after normalisation

    def test_alignment_marks_the_error(self):
        text = word_alignment("ես սիրում եմ կիթառ", "ես սիրում եմ կիտառ")
        self.assertIn("կիթառ", text)
        self.assertIn("կիտառ", text)
        self.assertIn("S", text)


if __name__ == "__main__":
    unittest.main()
