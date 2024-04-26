"""Library for handling transformations to discovery documents."""

from typing import Any, Dict


class Transformer:

  def transform(self, input_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Handles a specific transform of a parsed discover doc."""
    raise NotImplementedError()


class TransformNoOp(Transformer):
  """This transformer does nothing, it simply returns the input document."""

  def transform(self, input_doc: Dict[str, Any]) -> Dict[str, Any]:
    return input_doc


class TransformRedactElements(Transformer):
  """Redacts elements from a discovery document.

  The purpose of this transformer is to allow us to change the OP doc
  without affecting the existing merge process which expects legacy apiary
  to be the sole source of information for certain methods and resources.
  """

  def __init__(self, redactions):
    """Construct an instance of the redaction transformer.

    Supports specifying redactions as a list of strings, where the strings
    represent nodes with dot delimiters e.g. node.subnode.subnode

    Args:
      redactions: list of strings representing json nodes using periods as
        delimiters e.g. node.sub_node.redacted_node
    """
    self.redactions = redactions

  def transform(self, input_doc: Dict[str, Any]) -> Dict[str, Any]:
    for redaction in self.redactions:
      current = input_doc
      path = redaction.split('.')
      stopped = False
      while len(path) > 1:
        elem = path[0]
        if elem not in current:
          stopped = True
          break
        current = current[elem]
        path = path[1:]
      if not stopped and len(path) == 1:
        try:
          del current[path[0]]
        except KeyError:
          pass  # doesn't exist
    return input_doc


class TransformInjectElements(Transformer):
  """Injects elements into a discovery document.

  The purpose of this transformer is to allow us to inject values into a
  document at a given node.
  """

  def __init__(self, injections):
    """Construct an instance of the injection transformer.

    Args:
      injections: map keyed by dot-delimited location to inject, and value the
        dictionary content to inject
    """
    self.injections = injections

  def transform(self, input_doc: Dict[str, Any]) -> Dict[str, Any]:
    for key, content in self.injections.items():
      current = input_doc
      path = key.split('.')
      stopped = False
      while len(path) > 1:
        elem = path[0]
        if elem not in current:
          stopped = True
          break
        current = current[elem]
        path = path[1:]
      if not stopped and len(path) == 1:
        current[path[0]] = content
    return input_doc


class TransformPaths(Transformer):
  """Converts OP URL paths to legacy form."""

  def transform(self, input_doc: Dict[str, Any]) -> Dict[str, Any]:
    # normalize batchPath
    if input_doc['basePath']:
      input_doc['batchPath'] = 'batch' + input_doc['basePath']
    # ensure top-level fields are slash terminated.
    for node in ['basePath', 'baseUrl', 'servicePath']:
      val = input_doc[node]
      if not val.endswith('/'):
        input_doc[node] = val + '/'
    # ensure resource paths don't have leading slashes.
    for res in input_doc['resources'].values():
      for method in res['methods'].values():
        path = method['path']
        if path.startswith('/'):
          method['path'] = path[1:]
        flat = method['flatPath']
        if flat.startswith('/'):
          method['flatPath'] = flat[1:]
    return input_doc


class TransformRenameSchema(Transformer):
  """Renames a referenced schema type.

  The purpose of this transformer is to allow a rename of a schema
  type safely.  In order to successfully rename, we must do the following:

    * update the keyname in the schemas collection
    * update the schema id (it's generally the same)
    * walk the document and "$ref" fields to the new name, which may
      be present in schemas or in the resource methods request/response
      entries
  """

  def __init__(self, old_name, new_name):
    """Construct an instance of the redaction transformer.

    Supports specifying redactions as a list of strings, where the strings
    represent nodes with dot delimiters e.g. node.subnode.subnode

    Args:
      old_name: string representing the old schema name
      new_name: string representing the new schema name
    """
    self.old_name = old_name
    self.new_name = new_name

  def transform(self, input_doc: Dict[str, Any]) -> Dict[str, Any]:
    if not self.old_name:
      raise ValueError('invalid old name for rename transform')
    if not self.new_name:
      raise ValueError('invalid new name for rename transform')
    if self.old_name == self.new_name:
      raise ValueError('cannot rename using the same name')

    schemas = input_doc['schemas']
    if self.old_name not in schemas.keys():
      # no source schema to rename, so do nothing and return the original doc.
      return input_doc

    # rename schema
    schemas[self.new_name] = schemas[self.old_name]
    del schemas[self.old_name]

    # handle possible id rename
    msg = schemas[self.new_name]
    schema_id = msg.get('id')
    if schema_id == self.old_name:
      msg['id'] = self.new_name

    # process refs
    self._rename_refs(input_doc)
    return input_doc

  def _rename_refs(self, input_doc):
    for key, item in input_doc.items():
      if key == '$ref' and item == self.old_name:
        input_doc['$ref'] = self.new_name
      if isinstance(item, dict):
        self._rename_refs(item)