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
"""Provides a structured comparison mechanism for comparing two discovery documents."""

import enum
import hashlib
import json
from typing import Optional, List


class DifferenceType(enum.Enum):
  """DifferenceType categorizes the nature of a specific difference."""

  ADDED = 1
  DELETED = 2
  CHANGED = 3


class Difference:
  """Difference represents a specific difference between two discovery documents."""

  def __init__(self, location=None, diff_type=None):
    self.diff_type = diff_type
    self.location = location

  def __repr__(self):
    return 'Difference({}: {})'.format('.'.join(self.location), self.diff_type)

  def __eq__(self, other):
    if isinstance(other, Difference):
      return (
          self.location == other.location and self.diff_type == other.diff_type
      )
    return NotImplemented


class DiscoveryDocComparer:
  """DiscoveryDocComparer compares two documents.

  The comparer is instantiated with a reference doc.
  """

  IGNORED_NODES = [
      ['revision'],  # revision is expected to be different
  ]

  def __init__(self, reference_doc: Optional[bytes] = None):
    """Constructor."""
    if reference_doc is None:
      self.reference_doc = None
    else:
      self.reference_doc = json.loads(reference_doc)

  def compare_doc(self, new_doc: bytes) -> List[Difference]:
    """Generates the list of difference between documents."""
    if self.reference_doc is None:
      raise ValueError('no reference doc to compare against')
    new_doc = json.loads(new_doc)
    return self._compare([], self.reference_doc, new_doc)

  def _compare(self, parent, reference, new):
    """internal comparer."""
    diffs = []
    if isinstance(reference, dict):
      # We only descend through dictionaries/maps.  Discovery documents rely
      # heavily on maps/objects, and comparing more granularly with other data
      # types doesn't provide significant value.
      if not isinstance(new, dict):
        diffs.append(
            Difference(diff_type=DifferenceType.CHANGED, location=parent)
        )
        return diffs

      all_keys = set(reference.keys())
      all_keys.update(new.keys())

      for key in sorted(all_keys):
        path = parent + [key]
        old_subnode = reference.get(key, None)
        if old_subnode is None:
          diffs.append(
              Difference(diff_type=DifferenceType.ADDED, location=path)
          )
          continue
        new_subnode = new.get(key, None)
        if new_subnode is None:
          diffs.append(
              Difference(diff_type=DifferenceType.DELETED, location=path)
          )
          continue
        diff = self._diff(path, old_subnode, new_subnode)
        if diff is not None:
          # Because a difference is present, descend further into the document
          # to make it more granular.
          sub_parent = parent.copy()
          sub_parent.append(key)
          sub_diffs = self._compare(sub_parent, old_subnode, new_subnode)
          if sub_diffs:
            diffs.extend(sub_diffs)
          else:
            # TODO(shollyman): should we record coarser differences when
            # there's more granular differences?
            diffs.append(diff)
    return diffs

  def _diff(self, path, old, new):
    if path in self.IGNORED_NODES:
      return None
    old_hash = self._compute_hash(old)
    new_hash = self._compute_hash(new)
    if old_hash != new_hash:
      return Difference(
          diff_type=DifferenceType.CHANGED,
          location=path,
      )

  def _compute_hash(self, node) -> str:
    """Derive a hash value for a subset of a document."""
    return hashlib.md5(
        json.dumps(node, sort_keys=True).encode('utf-8')
    ).hexdigest()


class BreakingChangeDetector:
  """A minimal breaking change detector.

  This detector flags more egregious changes to a discovery document, but
  doesn't capture all the things we'd consider a breaking change from a
  consumer perspective.
  """

  def has_breaking_changes(self, diffs: List[Difference]) -> bool:
    for diff in diffs:
      if self.is_breaking(diff):
        return True
    return False

  def report_breaking_changes(
      self, diffs: List[Difference]
  ) -> List[Difference]:
    breaking = []
    for diff in diffs:
      if self.is_breaking(diff):
        breaking.append(diff)
    return breaking

  def is_breaking(self, diff: Difference) -> bool:
    if self._is_breaking_addressing_change(diff):
      return True
    if self._is_breaking_resource_change(diff):
      return True
    if self._is_breaking_schema_change(diff):
      return True
    return False

  def _is_breaking_addressing_change(self, diff: Difference) -> bool:
    """evaluates diffs related to URI paths."""
    if diff.location[0] in ['rootUrl', 'basePath', 'batchPath', 'mtlsRootUrl']:
      return True
    return False

  def _is_breaking_resource_change(self, diff: Difference) -> bool:
    """evaluates diffs related to the resources collection (API methods)."""
    if diff.location[0] != 'resources':
      return False
    if diff.diff_type == DifferenceType.DELETED:
      # opt outs for known deletions that aren't breaking
      if len(diff.location) == 5 and diff.location[-1] == 'scopes':
        # removal of per-method scope list
        return False
      # Flag all other deletions as breaking.
      return True
    return False

  def _is_breaking_schema_change(self, diff: Difference) -> bool:
    """evaluates diffs related to the schema collection (API types)."""
    if diff.location[0] != 'schemas':
      return False
    if diff.diff_type == DifferenceType.DELETED:
      # handle exceptional deletion cases:
      if diff.location[-1] in [
          'default',
          'annotations',
          'description',
          'enumDescriptions',
      ]:
        # The "safe" cases of delections which we don't flag.
        #
        # Deletion of "default" happens when we switch to reporting
        # enums rather than just the bare string. Similarly, removal of
        # "annotations" represent benign changes.  Deletion of "description"
        # nodes means a documentation change.
        return False
      # Flag all other deletions as breaking.
      return True
    if diff.diff_type == DifferenceType.CHANGED:
      # ignore description changes
      if diff.location[-1] in ['description', 'enumDescriptions']:
        return False
      return True
    return False