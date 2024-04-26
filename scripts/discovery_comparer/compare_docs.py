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
r"""compare_docs is a simple CLI driver for comparing two documents.
TODO(coleleah): update instructions
Example Usage:
  python compare_docs.py \
    --reference_file=cloud/helix/tools/discovery/testdata/apiary_fragment.json \
    --new_file=cloud/helix/tools/discovery/testdata/op_fragment.json

"""

import json
import os

from absl import app
from absl import flags

import comparer


_REFERENCE_FILE = flags.DEFINE_string(
    'reference_file',
    default=None,
    help='reference document to compare against',
    required=True,
)

_NEW_FILE = flags.DEFINE_string(
    'new_file',
    default=None,
    help='file with new document being compared',
    required=True,
)

_VERBOSE = flags.DEFINE_bool('verbose', default=False, help='verbose output')

_IGNORE_DESCRIPTIONS = flags.DEFINE_bool(
    'ignore_descriptions',
    default=False,
    help='ignore description node differences',
)


def _read_file(filename: str) -> bytes:
  with open(filename, 'rb') as f:
    return f.read()


def _render_doc(doc) -> str:
  return json.dumps(doc, indent=2, sort_keys=True)


def main(unused_argv) -> int:
  if len(unused_argv) > 1:
    raise app.UsageError('Too many command-line arguments.')
  reference_file = os.path.abspath(_REFERENCE_FILE.value)
  reference_doc = _read_file(reference_file)
  comp = comparer.DiscoveryDocComparer(reference_doc)
  new_file = os.path.abspath(_NEW_FILE.value)
  new_doc = _read_file(new_file)
  if _VERBOSE.value:
    ref_parsed = json.loads(reference_doc)
    new_parsed = json.loads(new_doc)
  diffs = comp.compare_doc(new_doc)
  if _IGNORE_DESCRIPTIONS.value and diffs:
    # redact all diffs that merely represent differences in documentation.
    diffs = [d for d in diffs if d.location[-1] != 'description']
  if diffs:
    print('{} Differences found'.format(len(diffs)))
    print('Reference file: {}'.format(reference_file))
    print('New File: {}'.format(new_file))
    if _IGNORE_DESCRIPTIONS.value:
      print('Documentation nodes (descriptions) suppressed')
    if _VERBOSE.value:
      print('Verbose output included')
    print('')
    for diff in diffs:
      print(diff)
      if _VERBOSE.value:
        # For verbose mode, we want to emit the specific textual difference.
        ref_source = ref_parsed
        new_source = new_parsed
        for path in diff.location:
          if diff.diff_type in [
              comparer.DifferenceType.DELETED,
              comparer.DifferenceType.CHANGED,
          ]:
            ref_source = ref_source[path]
          if diff.diff_type in [
              comparer.DifferenceType.ADDED,
              comparer.DifferenceType.CHANGED,
          ]:
            new_source = new_source[path]
        ref_rendered = _render_doc(ref_source)
        new_rendered = _render_doc(new_source)
        if diff.diff_type == comparer.DifferenceType.ADDED:
          print('----- added content -----\n{}\n'.format(new_rendered))
        if diff.diff_type == comparer.DifferenceType.DELETED:
          print('----- removed content -----\n{}\n'.format(ref_rendered))
        if diff.diff_type == comparer.DifferenceType.CHANGED:
          print(
              '----- reference content -----\n{}\n----- new content -----\n{}\n'
              .format(ref_rendered, new_rendered)
          )
    return 1
  else:
    print('no differences found')
    return 0


if __name__ == '__main__':
  app.run(main)