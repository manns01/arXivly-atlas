"""Offline unit tests for arxiv_text.py.  Run: python -m unittest discover tests"""

import unittest

from arxiv_text import (
    arxiv_id,
    author_spec_key,
    author_spec_matches,
    clean_abstract,
    name_key,
    name_keys_from_creator,
    normalize_text,
    surname_of,
    surnames_from_creator,
)


class NormalizeText(unittest.TestCase):
    def test_latex_accents_braced_and_bare(self):
        self.assertEqual(normalize_text(r"Mu\~{n}oz"), "Munoz")
        self.assertEqual(normalize_text(r"Hlo\v{z}ek"), "Hlozek")
        self.assertEqual(normalize_text(r"K\"uhnel"), "Kuhnel")
        self.assertEqual(normalize_text(r"\'Ecole"), "Ecole")
        self.assertEqual(normalize_text(r'Ali \"Ovg\"un'), "Ali Ovgun")

    def test_unicode_accents(self):
        self.assertEqual(normalize_text("Kühnel"), "Kuhnel")
        self.assertEqual(normalize_text("Muñoz"), "Munoz")
        self.assertEqual(normalize_text("Faà di Bruno"), "Faa di Bruno")

    def test_latex_special_letters(self):
        self.assertEqual(normalize_text(r"Wei\ss"), "Weiss")
        self.assertEqual(normalize_text(r"S\o rensen"), "Sorensen")
        self.assertEqual(normalize_text(r"\AA gren"), "Agren")

    def test_empty_and_whitespace(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("  a\n b  "), "a b")

    def test_plain_ascii_untouched(self):
        self.assertEqual(normalize_text("Smith"), "Smith")


class SurnameExtraction(unittest.TestCase):
    def test_first_middle_last(self):
        self.assertEqual(surname_of("Nikko John Leo S. Lobos"), "lobos")
        self.assertEqual(surname_of(r'Ali \"Ovg\"un'), "ovgun")

    def test_particles_fold_into_surname(self):
        self.assertEqual(surname_of("van der Bij"), "van der bij")
        self.assertEqual(surname_of("de Sitter"), "de sitter")

    def test_last_comma_first(self):
        self.assertEqual(surname_of("Einstein, Albert"), "einstein")

    def test_no_substring_collision(self):
        # "Hu" must not match inside "Hubble"
        self.assertNotEqual(surname_of("Edwin Hubble"), "hu")
        self.assertEqual(surname_of("Edwin Hubble"), "hubble")

    def test_creator_string_splits_on_commas(self):
        creator = r'Nikko John Leo S. Lobos, Ali \"Ovg\"un, Reggie C. Pantig'
        self.assertEqual(surnames_from_creator(creator), ["lobos", "ovgun", "pantig"])

    def test_empty(self):
        self.assertEqual(surnames_from_creator(""), [])
        self.assertEqual(surname_of(""), "")


class NameKeyAndAuthorSpec(unittest.TestCase):
    def test_name_key_initial_and_surname(self):
        self.assertEqual(name_key("Nikko John Leo S. Lobos"), ("n", "lobos"))
        self.assertEqual(name_key("C. Megan Urry"), ("c", "urry"))
        self.assertEqual(name_key("Felix J. Yu"), ("f", "yu"))
        self.assertEqual(name_key("Einstein, Albert"), ("a", "einstein"))

    def test_name_key_no_given_name(self):
        self.assertEqual(name_key("Hu"), ("", "hu"))

    def test_name_keys_from_creator(self):
        creator = "Djuna Croon, Sergio Sevillano Munoz, Miguel Zumalacarregui"
        self.assertEqual(
            name_keys_from_creator(creator),
            [["d", "croon"], ["s", "munoz"], ["m", "zumalacarregui"]],
        )

    def test_author_spec_key_forms(self):
        self.assertEqual(author_spec_key("Hu"), ("", "hu"))
        self.assertEqual(author_spec_key("W. Hu"), ("w", "hu"))
        self.assertEqual(author_spec_key("W Hu"), ("w", "hu"))
        self.assertEqual(author_spec_key("Wayne Hu"), ("w", "hu"))
        self.assertEqual(author_spec_key("van der Bij"), ("", "van der bij"))

    def test_spec_matches_bare_surname_any_initial(self):
        keys = [["z", "hu"], ["h", "yu"]]
        self.assertTrue(author_spec_matches(keys, author_spec_key("Hu")))

    def test_spec_matches_initial_form(self):
        keys = [["z", "hu"]]                       # Zhongtian Hu
        self.assertFalse(author_spec_matches(keys, author_spec_key("W. Hu")))
        self.assertTrue(author_spec_matches(keys, author_spec_key("Z. Hu")))

    def test_spec_surname_still_exact_not_substring(self):
        keys = [["e", "hubble"]]
        self.assertFalse(author_spec_matches(keys, author_spec_key("Hu")))

    def test_spec_empty_surname_never_matches(self):
        self.assertFalse(author_spec_matches([["e", "hubble"]], ("", "")))


class ArxivId(unittest.TestCase):
    def test_oai_id_strips_version(self):
        self.assertEqual(arxiv_id("oai:arXiv.org:2609.04254v1"), "2609.04254")

    def test_abs_url(self):
        self.assertEqual(arxiv_id("https://arxiv.org/abs/2609.04254"), "2609.04254")

    def test_old_style_id(self):
        self.assertEqual(arxiv_id("astro-ph/0501171v2"), "astro-ph/0501171")

    def test_no_id(self):
        self.assertEqual(arxiv_id("not an id"), "")


class CleanAbstract(unittest.TestCase):
    def test_strips_announce_preamble(self):
        raw = ("arXiv:2609.04254v1 Announce Type: new \nAbstract: We study a "
               "phenomenological fixed-ADM prescription.")
        self.assertEqual(
            clean_abstract(raw),
            "We study a phenomenological fixed-ADM prescription.",
        )

    def test_strips_cross_preamble(self):
        raw = "arXiv:2609.09999v2 Announce Type: cross \nAbstract: Foo bar."
        self.assertEqual(clean_abstract(raw), "Foo bar.")

    def test_no_preamble_passthrough(self):
        self.assertEqual(clean_abstract("Just an abstract."), "Just an abstract.")


if __name__ == "__main__":
    unittest.main()
