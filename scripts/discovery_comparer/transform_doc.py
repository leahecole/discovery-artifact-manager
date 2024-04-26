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
"""CLI for driving transforms of discovery document."""

import json
import os

from absl import app
from absl import flags

from google3.cloud.helix.tools.discovery import transformer
from google3.pyglib import gfile


_INPUT_FILE = flags.DEFINE_string(
    'input_file',
    default=None,
    help='input document to be transformed',
    required=True,
)

_OUTPUT_FILE = flags.DEFINE_string(
    'output_file',
    default=None,
    help='where output document should be written',
    required=True,
)

_TRANSFORM = flags.DEFINE_string(
    'transform',
    default=None,
    help='which transformation series to run',
    required=True,
)

_VERBOSE = flags.DEFINE_bool('verbose', default=False, help='verbose output')


# This is the set of redactions needed to achieve parity.
PREMERGE_REDACTION_LIST = [
    'schemas.ColumnReference',
    'schemas.CopyJobStatistics',
    'schemas.DataFormatOptions',
    'schemas.DmlStats',
    'schemas.ExportDataStatistics',
    'schemas.ExternalServiceCost',
    'schemas.FieldElementType',
    'schemas.ForeignKey',
    'schemas.GcpTag',
    'schemas.HighCardinalityJoin',
    'schemas.InputDataChange',
    'schemas.LinkedDatasetSource',
    'schemas.LoadQueryStatistics',
    'schemas.LoggingInfo',
    'schemas.MaterializedView',
    'schemas.MaterializedViewStatistics',
    'schemas.MaterializedViewStatus',
    'schemas.MetadataCacheStatistics',
    'schemas.ModelExtractOptions',
    'schemas.NumericId',
    'schemas.PerformanceInsights',
    'schemas.PrimaryKey',
    'schemas.QueryInfo',
    'schemas.Range',
    'schemas.ScriptOptions',
    'schemas.StagePerformanceChangeInsight',
    'schemas.StagePerformanceStandaloneInsight',
    'schemas.SystemVariables',
    'schemas.TableMetadataCacheUsage',
    'schemas.TableReplicationInfo',
    'schemas.ThriftOptions',
    'resources.datasets.methods.getIamPolicy',  # b/296612193
    'resources.datasets.methods.setIamPolicy',  # b/296612193
    'resources.datasets.methods.testIamPermissions',  # b/296612193
]

# BQML's preview was a bit chaotic, including features like exposing BQML models
# as tables.  This functionality has since been deprecated from the service
# definition, but to avoid breaking users we inject the representation into the
# discovery document.
LEGACY_BQML_SCHEMAS = {
    'schemas.BigQueryModelTraining': {
        'id': 'BigQueryModelTraining',
        'properties': {
            'currentIteration': {
                'description': 'Deprecated.',
                'format': 'int32',
                'type': 'integer',
            },
            'expectedTotalIterations': {
                'description': 'Deprecated.',
                'format': 'int64',
                'type': 'string',
            },
        },
        'type': 'object',
    },
    'schemas.BqmlIterationResult': {
        'id': 'BqmlIterationResult',
        'properties': {
            'durationMs': {
                'description': 'Deprecated.',
                'format': 'int64',
                'type': 'string',
            },
            'evalLoss': {
                'description': 'Deprecated.',
                'format': 'double',
                'type': 'number',
            },
            'index': {
                'description': 'Deprecated.',
                'format': 'int32',
                'type': 'integer',
            },
            'learnRate': {
                'description': 'Deprecated.',
                'format': 'double',
                'type': 'number',
            },
            'trainingLoss': {
                'description': 'Deprecated.',
                'format': 'double',
                'type': 'number',
            },
        },
        'type': 'object',
    },
    'schemas.BqmlTrainingRun': {
        'id': 'BqmlTrainingRun',
        'properties': {
            'iterationResults': {
                'description': 'Deprecated.',
                'items': {'$ref': 'BqmlIterationResult'},
                'type': 'array',
            },
            'startTime': {
                'description': 'Deprecated.',
                'format': 'date-time',
                'type': 'string',
            },
            'state': {'description': 'Deprecated.', 'type': 'string'},
            'trainingOptions': {
                'description': 'Deprecated.',
                'properties': {
                    'earlyStop': {'type': 'boolean'},
                    'l1Reg': {'format': 'double', 'type': 'number'},
                    'l2Reg': {'format': 'double', 'type': 'number'},
                    'learnRate': {'format': 'double', 'type': 'number'},
                    'learnRateStrategy': {'type': 'string'},
                    'lineSearchInitLearnRate': {
                        'format': 'double',
                        'type': 'number',
                    },
                    'maxIteration': {'format': 'int64', 'type': 'string'},
                    'minRelProgress': {'format': 'double', 'type': 'number'},
                    'warmStart': {'type': 'boolean'},
                },
                'type': 'object',
            },
        },
        'type': 'object',
    },
    'schemas.ModelDefinition': {
        'id': 'ModelDefinition',
        'properties': {
            'modelOptions': {
                'description': 'Deprecated.',
                'properties': {
                    'labels': {'items': {'type': 'string'}, 'type': 'array'},
                    'lossType': {'type': 'string'},
                    'modelType': {'type': 'string'},
                },
                'type': 'object',
            },
            'trainingRuns': {
                'description': 'Deprecated.',
                'items': {'$ref': 'BqmlTrainingRun'},
                'type': 'array',
            },
        },
        'type': 'object',
    },
    'schemas.JobStatistics2.properties.modelTraining': {
        '$ref': 'BigQueryModelTraining',
        'description': 'Deprecated.',
    },
    'schemas.JobStatistics2.properties.modelTrainingCurrentIteration': {
        'description': 'Deprecated.',
        'format': 'int32',
        'type': 'integer',
    },
    'schemas.JobStatistics2.properties.modelTrainingExpectedTotalIteration': {
        'description': 'Deprecated.',
        'format': 'int64',
        'type': 'string',
    },
    'schemas.Table.properties.model': {
        '$ref': 'ModelDefinition',
        'description': 'Deprecated.',
    },
}


# These are the transforms common to ALL api versions.
COMMON_TRANSFORM_LIST = [
    transformer.TransformPaths(),
    transformer.TransformRedactElements([
        'resources.datasets.methods.getIamPolicy',
        'resources.datasets.methods.setIamPolicy',
        'resources.datasets.methods.testIamPermissions',
        'resources.projects.resources',  # nested dataset IAM methods
    ]),  # b/296612193 - suppress dataset IAM methods
    transformer.TransformRenameSchema(
        old_name='DmlStats', new_name='DmlStatistics'
    ),
    transformer.TransformRenameSchema(
        old_name='CopyJobStatistics', new_name='JobStatistics5'
    ),
    transformer.TransformRenameSchema(
        old_name='LoggingInfo', new_name='SparkLoggingInfo'
    ),
    transformer.TransformRedactElements([
        'schemas.JobConfigurationLoad.properties.thriftOptions',
        'schemas.ThriftOptions',
    ]),  # b/293516145 - suppress thrift options
    transformer.TransformInjectElements(LEGACY_BQML_SCHEMAS),
    transformer.TransformInjectElements({
        'resources.jobs.methods.list.parameters.maxResults.format': 'uint32',
        'schemas.MaterializedViewDefinition.properties.refreshIntervalMs.format': (
            'int64'
        ),
    }),  # These are effectively hints to users, but not to code generators
    # about the contents of the field.  It may be possible to remove
    # them as they should not induce breaking changes.  The "type" of
    # these fields is json integer.
    transformer.TransformInjectElements({
        'schemas.DestinationTableProperties.properties.expirationTime': {
            'description': 'Internal use only.',
            'format': 'date-time',
            'type': 'string',
        },
    }),  # This is an internal only field added to legacy discovery, but
    # still under visibility guard in the service definition.
    transformer.TransformRedactElements([
        'schemas.TableConstraints.properties.foreignKeys.items.properties.referencedTable.$ref'
    ]),  # Part of a pair of legacy transforms.  This rule removes the "$ref"
    # node which would point the reference at another type in the
    # discovery schema list (schemas.DatasetReference).
    transformer.TransformInjectElements({
        'schemas.TableConstraints.properties.foreignKeys.items.properties.referencedTable': {
            'type': 'object',
            'properties': {
                'datasetId': {'type': 'string'},
                'projectId': {'type': 'string'},
                'tableId': {'type': 'string'},
            },
        }
    }),  # Second part of the paired transform.  This rule inlines the fields
    # of DatasetReference, as the legacy representation inside
    # TableConstraints -> ForeignKey is inlined.  This is the only instance
    # of an inlined DatasetReference, and we definitely can't inline all
    # the references.
    transformer.TransformInjectElements({
        'schemas.TableFieldSchema.properties.categories': {
            'description': 'Deprecated.',
            'properties': {
                'names': {
                    'description': 'Deprecated.',
                    'items': {'type': 'string'},
                    'type': 'array',
                }
            },
            'type': 'object',
        }
    }),  # deprecated but referenced in OSS projects (beam)
    transformer.TransformInjectElements({
        'schemas.QueryRequest.properties.continuous': {
            'description': (
                '[Optional] Specifies whether the query should be'
                ' executed as a continuous query. The default value is'
                ' false.'
            ),
            'type': 'boolean',
        },
        'schemas.JobConfigurationQuery.properties.continuous': {
            'description': (
                '[Optional] Specifies whether the query should be'
                ' executed as a continuous query. The default value is'
                ' false.'
            ),
            'type': 'boolean',
        },
    }),  # temporary visibility mismatch, can go away after continuous
    # query launches and removes the visibility restriction.
    transformer.TransformInjectElements({
        'schemas.MaterializedViewDefinition.properties.maxStaleness': {
            'description': (
                '[Optional] Max staleness of data that could be'
                ' returned when materizlized view is queried (formatted'
                ' as Google SQL Interval type).'
            ),
            'format': 'byte',
            'type': 'string',
        },
        'schemas.Table.properties.resourceTags': {
            'additionalProperties': {'type': 'string'},
            'description': (
                '[Optional] The tags associated with this table. Tag keys are'
                ' globally unique. See additional information on'
                ' [tags](https://cloud.google.com/iam/docs/tags-access-control#definitions).'
                ' An object containing a list of "key": value pairs. The key is'
                ' the namespaced friendly name of the tag key, e.g.'
                ' "12345/environment" where 12345 is parent id. The value is'
                ' the friendly short name of the tag value, e.g. "production".'
            ),
            'type': 'object',
        },
    }),  # temporary visibility settings
    transformer.TransformRedactElements([
        'resources.tables.methods.patch.parameters.autodetectSchema',
        'resources.tables.methods.update.parameters.autodetectSchema',
    ]),  # redact the correct form, as not all generators normalize query params
    transformer.TransformInjectElements({
        'resources.tables.methods.patch.parameters.autodetect_schema': {
            'description': (
                'Optional.  When true will autodetect schema, else will keep'
                ' original schema'
            ),
            'location': 'query',
            'type': 'boolean',
        },
        'resources.tables.methods.update.parameters.autodetect_schema': {
            'description': (
                'Optional.  When true will autodetect schema, else will keep'
                ' original schema'
            ),
            'location': 'query',
            'type': 'boolean',
        },
    }),  # re-inject the old format for autodetect (paired with above redaction)
    transformer.TransformInjectElements({
        'resources.jobs.methods.list.parameters.projection.enum': [
            'full',
            'minimal',
        ],
        'resources.jobs.methods.list.parameters.projection.enumDescriptions': [
            'Includes all job data',
            'Does not include the job configuration',
        ],
        'resources.jobs.methods.list.parameters.stateFilter.enum': [
            'done',
            'pending',
            'running',
        ],
        'resources.jobs.methods.list.parameters.stateFilter.enumDescriptions': [
            'Finished jobs',
            'Pending jobs',
            'Running jobs',
        ],
    }),  # overload legacy enums to report both capitalization forms
    transformer.TransformInjectElements({
        'schemas.SnapshotDefinition.properties.snapshotTime.format': (
            'date-time'
        ),
        'schemas.CloneDefinition.properties.cloneTime.format': 'date-time',
    }),  # deal with java inconsistency between date-time and google-datetime
    transformer.TransformRedactElements([
        'schemas.TableList.properties.tables.items.properties.hivePartitioningOptions',
    ]),  # b/319110374
]

AVAILABLE_TRANSFORMS = {
    'default': [transformer.TransformNoOp()],
    'premerge-op': [
        transformer.TransformRedactElements(PREMERGE_REDACTION_LIST),
    ],
    'transform-op-v2test': COMMON_TRANSFORM_LIST + [
        transformer.TransformInjectElements({
            'mtlsRootUrl': 'https://test-bigquery.mtls.sandbox.google.com/',
        }),
    ],
    'transform-op-vnext': COMMON_TRANSFORM_LIST,
    'transform-op-vnexttest': COMMON_TRANSFORM_LIST,
    'transform-op-v2': COMMON_TRANSFORM_LIST,
}


def _read_file(filename: str) -> bytes:
  with gfile.GFile(filename, 'rb') as f:
    return f.read()


def _write_output(filename: str, output) -> None:
  with gfile.GFileText(filename, 'wt') as f:
    json.dump(output, f, indent=2, sort_keys=True)


def main(unused_argv) -> int:
  if len(unused_argv) > 1:
    raise app.UsageError('Too many command-line arguments.')
  if _TRANSFORM.value not in AVAILABLE_TRANSFORMS:
    raise app.UsageError(
        'invalid transform {} specified, available transforms: {}'.format(
            _TRANSFORM.value, AVAILABLE_TRANSFORMS.keys()
        )
    )

  input_file = os.path.abspath(_INPUT_FILE.value)
  input_data = _read_file(input_file)
  input_doc = json.loads(input_data)

  output_doc = None
  for step in AVAILABLE_TRANSFORMS[_TRANSFORM.value]:
    if _VERBOSE.value:
      print('running transform step {}'.format(step.__class__.__name__))
    output_doc = step.transform(input_doc)
    if output_doc is None:
      raise ValueError(
          'step failed to return document: {}'.format(step.__class__.__name__)
      )
    input_doc = output_doc

  output_file = os.path.abspath(_OUTPUT_FILE.value)

  try:
    _write_output(output_file, output_doc)
  except Exception as e:  # pylint: disable=broad-exception-caught
    print('Failed to write output to {}: {}'.format(output_file, str(e)))
    return 1
  return 0


if __name__ == '__main__':
  app.run(main)