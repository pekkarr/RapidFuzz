from itertools import product
from functools import partial
from string import ascii_letters, digits, punctuation

from hypothesis import given, assume, settings
import hypothesis.strategies as st
import pytest

from rapidfuzz import fuzz, process, utils, string_metric
from rapidfuzz.distance import Levenshtein, Indel
import random
import numpy as np

def isclose(a, b, rel_tol=1e-09, abs_tol=0.0):
    return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)

def levenshtein(s1, s2, weights=(1, 1, 1)):
    """
    python implementation of a generic Levenshtein distance
    this is much less error prone, than the bitparallel C implementations
    and is therefor used to test the C implementation
    However this makes this very slow even for testing purposes
    """

    rows = len(s1)+1
    cols = len(s2)+1
    insert, delete, substitute = weights

    dist = [[0 for x in range(cols)] for x in range(rows)]

    for row in range(1, rows):
        dist[row][0] = row * delete

    for col in range(1, cols):
        dist[0][col] = col * insert

    for col in range(1, cols):
        for row in range(1, rows):
            if s1[row-1] == s2[col-1]:
                cost = 0
            else:
                cost = substitute

            dist[row][col] = min(
                dist[row-1][col] + delete,  # deletion
                dist[row][col-1] + insert,  # insertion
                dist[row-1][col-1] + cost    # substitution
            )

    return dist[-1][-1]

def normalize_distance(dist, s1, s2, weights=(1, 1, 1)):
    insert, delete, substitute = weights
    if len(s1) > len(s2):
        max_dist = min([
            # delete all characters from s1 and insert all characters from s2
            len(s1) * delete + len(s2) * insert,
            # replace all characters and delete the remaining characters from s1
            len(s2) * substitute + (len(s1) - len(s2)) * delete
        ])
    else:
        max_dist = min([
            # delete all characters from s1 and insert all characters from s2
            len(s1) * delete + len(s2) * insert,
            # replace all characters and insert the remaining characters into s1
            len(s1) * substitute + (len(s2) - len(s1)) * insert
        ])

    return 100 - 100 * float(dist) / float(max_dist) if max_dist else 100

def partial_ratio_short_needle(s1, s2):
    if not s1 and not s2:
        return 100

    if not s1 or not s2:
        return 0

    if len(s1) > len(s2):
        return partial_ratio_short_needle(s2, s1)
    parts = [s2[max(0, i) : min(len(s2), i+len(s1))] for i in range(-len(s1), len(s2))]
    res = 0
    for part in parts:
        res = max(res, fuzz.ratio(s1, part))
    return res

def cdist_scorer(queries, choices, scorer):
    matrix = np.zeros((len(queries), len(choices)), dtype=np.uint8)

    for i, query in enumerate(queries):
        for j, choice in enumerate(choices):
            matrix[i, j] = scorer(query, choice)

    return matrix

def cdist_distance(queries, choices, scorer):
    matrix = np.zeros((len(queries), len(choices)), dtype=np.int32)

    for i, query in enumerate(queries):
        for j, choice in enumerate(choices):
            matrix[i, j] = scorer(query, choice)

    return matrix

def extractOne_scorer(s1, s2, scorer, processor=None, **kwargs):
    return process.extractOne(s1, [s2], processor=processor, scorer=scorer, **kwargs)[1]

def extract_scorer(s1, s2, scorer, processor=None, **kwargs):
    return process.extract(s1, [s2], processor=processor, scorer=scorer, **kwargs)[0][1]

def extract_iter_scorer(s1, s2, scorer, processor=None, **kwargs):
    return list(process.extract_iter(s1, [s2], processor=processor, scorer=scorer, **kwargs))[0][1]

def apply_editops(s1, s2, ops):
    new_str = ''
    s1_pos = 0
    for op in ops:
        j = op[1] - s1_pos
        while j:
            new_str += s1[s1_pos]
            s1_pos += 1
            j -= 1

        if op[0] == 'delete':
            s1_pos += 1
        elif op[0] == 'insert':
            new_str += s2[op[2]]
        elif op[0] == 'replace':
            new_str += s2[op[2]]
            s1_pos += 1

    j = len(s1) - s1_pos
    while j:
        new_str += s1[s1_pos]
        s1_pos += 1
        j -= 1

    return new_str


HYPOTHESIS_ALPHABET = ascii_letters + digits + punctuation

SCORERS = [
    fuzz.ratio,
    fuzz.partial_ratio,
    fuzz.token_set_ratio,
    fuzz.token_sort_ratio,
    fuzz.token_ratio,
    fuzz.partial_token_set_ratio,
    fuzz.partial_token_sort_ratio,
    fuzz.partial_token_ratio,
    fuzz.WRatio,
    fuzz.QRatio
]

FULL_SCORERS = [
    fuzz.ratio,
    fuzz.WRatio,
    fuzz.QRatio
]

PROCESSORS = [
    lambda x: x,
    utils.default_process
]

@given(s1=st.text(), s2=st.text())
@settings(max_examples=100, deadline=None)
def test_levenshtein_editops(s1, s2):
    """
    test Levenshtein.editops with any sizes
    """
    ops = Levenshtein.editops(s1, s2)
    assert apply_editops(s1, s2, ops) == s2

@given(s1=st.text(min_size=65), s2=st.text(min_size=65))
@settings(max_examples=50, deadline=None)
def test_levenshtein_editops_block(s1, s2):
    """
    test Levenshtein.editops for long strings
    """
    ops = Levenshtein.editops(s1, s2)
    assert apply_editops(s1, s2, ops) == s2

@given(s1=st.text(), s2=st.text())
@settings(max_examples=100, deadline=None)
def test_indel_editops(s1, s2):
    """
    test Indel.editops with any sizes
    """
    ops = Indel.editops(s1, s2)
    assert apply_editops(s1, s2, ops) == s2

@given(s1=st.text(min_size=65), s2=st.text(min_size=65))
@settings(max_examples=50, deadline=None)
def test_indel_editops_block(s1, s2):
    """
    test Indel.editops for long strings
    """
    ops = Indel.editops(s1, s2)
    assert apply_editops(s1, s2, ops) == s2

@given(s1=st.text(max_size=64), s2=st.text())
@settings(max_examples=50, deadline=1000)
def test_partial_ratio_short_needle(s1, s2):
    """
    test partial_ratio for short needles (needle <= 64)
    """
    assert isclose(fuzz.partial_ratio(s1, s2), partial_ratio_short_needle(s1, s2))

@given(s1=st.text(), s2=st.text())
@settings(max_examples=50, deadline=1000)
def test_token_ratio(s1, s2):
    """
    token_ratio should be max(token_sort_ratio, token_set_ratio)
    """
    assert fuzz.token_ratio(s1, s2) == max(fuzz.token_sort_ratio(s1, s2), fuzz.token_set_ratio(s1, s2))

@given(s1=st.text(), s2=st.text())
@settings(max_examples=50, deadline=1000)
def test_partial_token_ratio(s1, s2):
    """
    partial_token_ratio should be max(partial_token_sort_ratio, partial_token_set_ratio)
    """
    assert fuzz.partial_token_ratio(s1, s2) == max(fuzz.partial_token_sort_ratio(s1, s2), fuzz.partial_token_set_ratio(s1, s2))


@given(s1=st.text(max_size=64), s2=st.text(max_size=64))
@settings(max_examples=50, deadline=None)
def test_levenshtein_word(s1, s2):
    """
    Test short Levenshtein implementation against simple implementation
    """
    # uniform Levenshtein
    # distance
    reference_dist = levenshtein(s1, s2)
    assert string_metric.levenshtein(s1, s2) == reference_dist
    assert extractOne_scorer(  s1, s2, string_metric.levenshtein) == reference_dist
    assert extract_scorer(     s1, s2, string_metric.levenshtein) == reference_dist
    assert extract_iter_scorer(s1, s2, string_metric.levenshtein) == reference_dist
    # normalized distance
    reference_sim = normalize_distance(reference_dist, s1, s2)
    assert isclose(string_metric.normalized_levenshtein(s1, s2), reference_sim)
    assert isclose(extractOne_scorer(  s1, s2, string_metric.normalized_levenshtein), reference_sim)
    assert isclose(extract_scorer(     s1, s2, string_metric.normalized_levenshtein), reference_sim)
    assert isclose(extract_iter_scorer(s1, s2, string_metric.normalized_levenshtein), reference_sim)

    # InDel-Distance
    # distance
    reference_dist = levenshtein(s1, s2, weights=(1,1,2))
    assert string_metric.levenshtein(s1, s2, weights=(1,1,2)) == reference_dist
    assert extractOne_scorer(  s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    assert extract_scorer(     s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    assert extract_iter_scorer(s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    # normalized distance
    reference_sim = normalize_distance(reference_dist, s1, s2, weights=(1,1,2))
    assert isclose(string_metric.normalized_levenshtein(s1, s2, weights=(1,1,2)), reference_sim)
    assert isclose(extractOne_scorer(  s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)
    assert isclose(extract_scorer(     s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)
    assert isclose(extract_iter_scorer(s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)


@given(s1=st.text(min_size=65), s2=st.text(min_size=65))
@settings(max_examples=50, deadline=None)
def test_levenshtein_block(s1, s2):
    """
    Test blockwise Levenshtein implementation against simple implementation
    """
    # uniform Levenshtein
    # distance
    reference_dist = levenshtein(s1, s2)
    assert string_metric.levenshtein(s1, s2) == reference_dist
    assert extractOne_scorer(  s1, s2, string_metric.levenshtein) == reference_dist
    assert extract_scorer(     s1, s2, string_metric.levenshtein) == reference_dist
    assert extract_iter_scorer(s1, s2, string_metric.levenshtein) == reference_dist
    # normalized distance
    reference_sim = normalize_distance(reference_dist, s1, s2)
    assert isclose(string_metric.normalized_levenshtein(s1, s2), reference_sim)
    assert isclose(extractOne_scorer(  s1, s2, string_metric.normalized_levenshtein), reference_sim)
    assert isclose(extract_scorer(     s1, s2, string_metric.normalized_levenshtein), reference_sim)
    assert isclose(extract_iter_scorer(s1, s2, string_metric.normalized_levenshtein), reference_sim)

    # InDel-Distance
    # distance
    reference_dist = levenshtein(s1, s2, weights=(1,1,2))
    assert string_metric.levenshtein(s1, s2, weights=(1,1,2)) == reference_dist
    assert extractOne_scorer(  s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    assert extract_scorer(     s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    assert extract_iter_scorer(s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    # normalized distance
    reference_sim = normalize_distance(reference_dist, s1, s2, weights=(1,1,2))
    assert isclose(string_metric.normalized_levenshtein(s1, s2, weights=(1,1,2)), reference_sim)
    assert isclose(extractOne_scorer(  s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)
    assert isclose(extract_scorer(     s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)
    assert isclose(extract_iter_scorer(s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)

@given(s1=st.text(), s2=st.text())
@settings(max_examples=50, deadline=None)
def test_levenshtein_random(s1, s2):
    """
    Test mixed strings to test through all implementations of Levenshtein
    """
    # uniform Levenshtein
    # distance
    reference_dist = levenshtein(s1, s2)
    assert string_metric.levenshtein(s1, s2) == reference_dist
    assert extractOne_scorer(  s1, s2, string_metric.levenshtein) == reference_dist
    assert extract_scorer(     s1, s2, string_metric.levenshtein) == reference_dist
    assert extract_iter_scorer(s1, s2, string_metric.levenshtein) == reference_dist
    # normalized distance
    reference_sim = normalize_distance(reference_dist, s1, s2)
    assert isclose(string_metric.normalized_levenshtein(s1, s2), reference_sim)
    assert isclose(extractOne_scorer(  s1, s2, string_metric.normalized_levenshtein), reference_sim)
    assert isclose(extract_scorer(     s1, s2, string_metric.normalized_levenshtein), reference_sim)
    assert isclose(extract_iter_scorer(s1, s2, string_metric.normalized_levenshtein), reference_sim)

    # InDel-Distance
    # distance
    reference_dist = levenshtein(s1, s2, weights=(1,1,2))
    assert string_metric.levenshtein(s1, s2, weights=(1,1,2)) == reference_dist
    assert extractOne_scorer(  s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    assert extract_scorer(     s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    assert extract_iter_scorer(s1, s2, string_metric.levenshtein, weights=(1,1,2)) == reference_dist
    # normalized distance
    reference_sim = normalize_distance(reference_dist, s1, s2, weights=(1,1,2))
    assert isclose(string_metric.normalized_levenshtein(s1, s2, weights=(1,1,2)), reference_sim)
    assert isclose(extractOne_scorer(  s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)
    assert isclose(extract_scorer(     s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)
    assert isclose(extract_iter_scorer(s1, s2, string_metric.normalized_levenshtein, weights=(1,1,2)), reference_sim)

@given(sentence=st.text())
@settings(max_examples=50, deadline=1000)
def test_multiple_processor_runs(sentence):
    """
    Test that running a preprocessor on a sentence
    a second time does not change the result
    """
    assert utils.default_process(sentence) \
        == utils.default_process(utils.default_process(sentence))


@pytest.mark.parametrize('scorer,processor', list(product(FULL_SCORERS, PROCESSORS)))
@given(choices=st.lists(st.text(), min_size=1))
@settings(max_examples=50, deadline=1000)
def test_only_identical_strings_extracted(scorer, processor, choices):
    """
    Test that only identical (post processing) strings score 100 on the test.
    If two strings are not identical then using full comparison methods they should
    not be a perfect (100) match.
    :param scorer:
    :param processor:
    :param data:
    :return:
    """
    query = random.choice(choices)
    assume(processor(query) != '')

    matches = process.extract(query, choices,
        scorer=scorer, processor=processor,
        score_cutoff=100, limit=None)

    assert matches != []

    for match in matches:
        assert processor(query) == processor(match[0])


@given(queries=st.lists(st.text(), min_size=1), choices=st.lists(st.text(), min_size=1))
@settings(max_examples=50, deadline=1000)
def test_cdist(queries, choices):
    """
    Test that cdist returns correct results
    """

    reference_matrix = cdist_distance(queries, choices, scorer=string_metric.levenshtein)
    matrix = process.cdist(queries, choices, scorer=string_metric.levenshtein)
    assert (matrix == reference_matrix).all()

    reference_matrix = cdist_distance(queries, queries, scorer=string_metric.levenshtein)
    matrix = process.cdist(queries, queries, scorer=string_metric.levenshtein)
    assert (matrix == reference_matrix).all()
