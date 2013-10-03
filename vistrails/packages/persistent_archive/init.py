from file_archive import FileStore
import os

from vistrails.core.bundles.pyimport import py_import
from vistrails.core.system import current_dot_vistrails

from .common import set_default_store, PersistentHash
from .cache import CachedPath, CachedFile, CachedDir
from .queries import QueryCondition, QueryStringEqual, \
    QueryIntEqual, QueryIntRange, \
    Metadata, MetadataString, MetadataInt
from .persistedinput import PersistedInputPath, \
    PersistedInputFile, PersistedInputDir
from .queriedinput import QueriedInputPath, QueriedInputFile, QueriedInputDir

file_archive = py_import('file_archive', {
        'pip': 'file_archive'})


def initialize():
    if configuration.check('file_store'):
        file_store_path = configuration.file_store
    else:
        file_store_path = os.path.join(current_dot_vistrails(), 'file_archive')
    if not os.path.exists(file_store_path) or not os.listdir(file_store_path):
        FileStore.create_store(file_store_path)
    set_default_store(FileStore(file_store_path))


_modules = [
        # Reference to a specific file
        PersistentHash,

        # Caching modules
        (CachedPath, {'abstract': True}),
        CachedFile,
        CachedDir,

        # Condition modules
        (QueryCondition, {'abstract': True}),
        QueryStringEqual,
        QueryIntEqual,
        QueryIntRange,

        # Metadata modules
        (Metadata, {'abstract': True}),
        MetadataString,
        MetadataInt,

        # Input modules
        (PersistedInputPath, {'abstract': True}),
        PersistedInputFile,
        PersistedInputDir,

        # Query modules
        (QueriedInputPath, {'abstract': True}),
        QueriedInputFile,
        QueriedInputDir,
    ]
