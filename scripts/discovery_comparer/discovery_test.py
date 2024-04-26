# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for discovery functionality."""

import json

from comparer import BreakingChangeDetector
from comparer import Difference
from comparer import DifferenceType
from comparer import DiscoveryDocComparer
from transformer import TransformInjectElements
from transformer import TransformNoOp
from transformer import TransformRedactElements
from transformer import TransformRenameSchema
import unittest

TEST_DATA = {
    'apiary_fragment': (
        'testdata/apiary_fragment.json'
    ),
    'op_fragment': (
        'testdata/op_fragment.json'
    ),
    'merged': 'testdata/merged.json',
    'pre_rename': (
        'testdata/pre_rename.json'
    ),
    'post_rename': (
        'testdata/post_rename.json'
    ),
}


class DiscoveryDocComparerTest(unittest.TestCase):

  def test_compare_noreference(self):
    with open(TEST_DATA['apiary_fragment'], 'rb') as f:
       doc = f.read()
    comparer = DiscoveryDocComparer()
    with self.assertRaises(ValueError):
        comparer.compare_doc(doc)

  def test_compare_same(self):
    with open(TEST_DATA['apiary_fragment'], 'rb') as f:
        doc = f.read()
    comparer = DiscoveryDocComparer(doc)
    diffs = comparer.compare_doc(doc)
    self.assertEqual(len(diffs), 0)

  def test_compare_same_unsorted(self):
    comparer = DiscoveryDocComparer(b'{"foo": "bar", "baz": "banjo"}')
    diffs = comparer.compare_doc(b'{"baz": "banjo", "foo": "bar"}')
    self.assertEqual(len(diffs), 0)

  def test_compare_key_changed(self):
    comparer = DiscoveryDocComparer(b'{"foo": "bar"}')
    diffs = comparer.compare_doc(b'{"foo": {"bar": "baz"}}')
    self.assertEqual(len(diffs), 1)
    self.assertEqual(Difference(['foo'], DifferenceType.CHANGED), diffs[0])

  def test_compare_key_added(self):
    comparer = DiscoveryDocComparer(b'{"foo": "bar"}')
    diffs = comparer.compare_doc(b'{"foo": "bar", "baz": "banjo"}')
    self.assertEqual(len(diffs), 1)
    self.assertEqual(Difference(['baz'], DifferenceType.ADDED), diffs[0])

  def test_compare_key_removed(self):
    comparer = DiscoveryDocComparer(b'{"foo": "bar", "baz": "banjo"}')
    diffs = comparer.compare_doc(b'{"foo": "bar"}')
    self.assertEqual(len(diffs), 1)
    self.assertEqual(Difference(['baz'], DifferenceType.DELETED), diffs[0])

  def test_compare_nested(self):
    comparer = DiscoveryDocComparer(b'{"foo": {"bar": {"baz": "hello"}}}')
    diffs = comparer.compare_doc(b'{"foo": {"bar": {"baz": "goodbye"}}}')
    self.assertEqual(len(diffs), 1)
    self.assertEqual(
        Difference(['foo', 'bar', 'baz'], DifferenceType.CHANGED), diffs[0]
    )

  def test_compare_fragments(self):
    with open(TEST_DATA['apiary_fragment'], 'rb') as reffile:
        refdoc = reffile.read()
    with open(TEST_DATA['op_fragment'], 'rb') as testfile:
        testdoc = testfile.read()
    comparer = DiscoveryDocComparer(refdoc)
    diffs = comparer.compare_doc(testdoc)

    self.assertNotEqual(len(diffs),0)
    wanted_diffs = [
        Difference(['basePath'], DifferenceType.ADDED),
        Difference(['baseUrl'], DifferenceType.ADDED),
        Difference(['mtlsRootUrl'], DifferenceType.ADDED),
        Difference(
            ['resources', 'resourceA', 'methods', 'get', 'flatPath'],
            DifferenceType.ADDED,
        ),
        Difference(
            ['resources', 'resourceA', 'methods', 'get', 'path'],
            DifferenceType.CHANGED,
        ),
        Difference(['resources', 'resourceOpOnly'], DifferenceType.ADDED),
        Difference(['rootUrl'], DifferenceType.ADDED),
        Difference(['schemas', 'DatasetAccessEntry'], DifferenceType.DELETED),
        Difference(['schemas', 'test'], DifferenceType.ADDED),
        Difference(['servicePath'], DifferenceType.CHANGED),
        Difference(['test'], DifferenceType.DELETED),
    ]
    self.assertListEqual(diffs, wanted_diffs)
    self.assertNotIn(Difference(['revision'], DifferenceType.CHANGED), diffs)

  def test_breaking_changes(self):
    benign_diffs = [
        Difference(['baz'], DifferenceType.ADDED),
        Difference(['foo'], DifferenceType.CHANGED),
        Difference(['schemas', 'foo', 'description'], DifferenceType.CHANGED),
        Difference(['schemas', 'bar', 'description'], DifferenceType.DELETED),
        Difference(['schemas', 'bar', 'description'], DifferenceType.ADDED),
        Difference(['schemas', 'bar'], DifferenceType.ADDED),
        Difference(['resources', 'thing'], DifferenceType.ADDED),
        Difference(
            ['resources', 'foo', 'methods', 'get', 'scopes'],
            DifferenceType.DELETED,
        ),
        # a spurious key in the dictionary no one consumes
        Difference(['nonsense', 'madness'], DifferenceType.DELETED),
        Difference(
            ['schemas', 'foo', 'properties', 'somefield', 'description'],
            DifferenceType.CHANGED,
        ),
        Difference(
            ['schemas', 'foo', 'properties', 'enumfield', 'enumDescriptions'],
            DifferenceType.CHANGED,
        ),
        Difference(
            ['schemas', 'foo', 'properties', 'enumfield', 'enumDescriptions'],
            DifferenceType.DELETED,
        ),
    ]

    breaking_diffs = [
        Difference(['rootUrl'], DifferenceType.CHANGED),
        Difference(['basePath'], DifferenceType.CHANGED),
        Difference(['resources', 'otherthing'], DifferenceType.DELETED),
        Difference(['resources', 'foo', 'insert'], DifferenceType.DELETED),
        Difference(['schemas', 'foo'], DifferenceType.DELETED),
        Difference(
            ['schemas', 'foo', 'properties', 'some_field'],
            DifferenceType.DELETED,
        ),
        Difference(
            ['schemas', 'foo', 'properties', 'somefield', '$ref'],
            DifferenceType.CHANGED,
        ),
    ]

    bcd = BreakingChangeDetector()

    for diff in benign_diffs:
      self.assertFalse(bcd.is_breaking(diff), diff)
    self.assertFalse(bcd.has_breaking_changes(benign_diffs))

    for diff in breaking_diffs:
      self.assertTrue(bcd.is_breaking(diff), diff)
    self.assertTrue(bcd.has_breaking_changes(breaking_diffs))
    self.assertEqual(
        len(bcd.report_breaking_changes(breaking_diffs)), len(breaking_diffs)
    )

    combined = benign_diffs + breaking_diffs
    self.assertTrue(bcd.has_breaking_changes(combined))
    self.assertEqual(len(bcd.report_breaking_changes(combined)), len(breaking_diffs))


class TransformerTests(unittest.TestCase):

  def test_transform_noop(self):
    with open(TEST_DATA['merged'], 'rb') as f:
        input_resource = f.read()
    input_doc = json.loads(input_resource)
    output_doc = TransformNoOp().transform(input_doc)
    self.assertEqual(input_doc, output_doc)

  def test_transform_injection(self):
    input_doc = json.loads(b"""
        {
            "foo": {
                "bar": {
                    "baz": "hello",
                    "boop": "beep"
                }
            }
        }
        """)
    output_doc = TransformInjectElements({
        'foo.bar.new': {'thing': 'ding'},
        'rootfield': 'someval',
    }).transform(input_doc)
    expected = json.loads(b"""
        {
            "rootfield": "someval",
            "foo": {
                "bar": {
                    "baz": "hello",
                    "boop": "beep",
                    "new": {
                        "thing": "ding"
                    }
                }
            }
        }
        """)
    self.assertEqual(expected, output_doc)

  def test_transform_rename_schema(self):
    with open(TEST_DATA['pre_rename'], 'rb') as pre_file:
        pre_resource = pre_file.read()
    pre_rename = json.loads(pre_resource)
    with open(TEST_DATA['post_rename'], 'rb') as post_file:
        post_resource = post_file.read()
    post_rename = json.loads(post_resource)
    output_doc = TransformRenameSchema(
        old_name='SomeType', new_name='NewType'
    ).transform(pre_rename)
    self.assertEqual(post_rename, output_doc)

  def test_transform_rename_schema_no_source_schema(self):
    with open(TEST_DATA['pre_rename'], 'rb') as f:
       doc_resource = f.read()
    doc = json.loads(doc_resource)
    output_doc = TransformRenameSchema(
        old_name='NotPresentType', new_name='RenamedNotPresentType'
    ).transform(doc)
    self.assertEqual(doc, output_doc)

  def test_transform_redaction(self):
    input_doc = json.loads(
        b'{"foo": {"bar": {"baz": "hello", "boop": "beep"}}}'
    )
    output_doc = TransformRedactElements([
        'foo.bar.baz',
        'does.not.exist',
    ]).transform(input_doc)
    expected = json.loads(b'{"foo": {"bar": {"boop": "beep"}}}')
    self.assertEqual(expected, output_doc)


if __name__ == '__main__':
  unittest.main()