###########################################################################
##
## Copyright (C) 2006-2007 University of Utah. All rights reserved.
##
## This file is part of VisTrails.
##
## This file may be used under the terms of the GNU General Public
## License version 2.0 as published by the Free Software Foundation
## and appearing in the file LICENSE.GPL included in the packaging of
## this file.  Please review the following to ensure GNU General Public
## Licensing requirements will be met:
## http://www.opensource.org/licenses/gpl-license.php
##
## If you are unsure which license is appropriate for your use (for
## instance, you are interested in developing a commercial derivative
## of VisTrails), please contact us at vistrails@sci.utah.edu.
##
## This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
## WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
##
############################################################################
################################################################################
# VTK Package for VisTrails
################################################################################

"""The Visualization ToolKit (VTK) is an open source, freely available
software system for 3D computer graphics, image processing, and
visualization used by thousands of researchers and developers around
the world. http://www.vtk.org"""

from core.bundles import py_import

vtk = py_import('vtk', {'linux-ubuntu': 'python-vtk',
                        'linux-fedora': 'vtk-python'})

from core.utils import all, any, VistrailsInternalError, InstanceObject
from core.debug import log
from core.modules.basic_modules import Integer, Float, String, File, \
     Variant, Color
from core.modules.module_registry import (registry, add_module,
                                          has_input_port,
                                          add_input_port, add_output_port)
from core.modules.vistrails_module import new_module, ModuleError
from base_module import vtkBaseModule
from class_tree import ClassTree
from vtk_parser import VTKMethodParser
import re
import os.path
from itertools import izip
from vtkcell import VTKCell
import tf_widget
import offscreen
import fix_classes
import inspectors
from hasher import vtk_hasher

version = '0.9.1'
identifier = 'edu.utah.sci.vistrails.vtk'
name = 'VTK'

################################################################################

# filter some deprecation warnings coming from the fact that vtk calls
# range() with float parameters

import warnings
warnings.filterwarnings("ignore",
                        message="integer argument expected, got float")

################################################################################

def get_description_class(klass):
    """Because sometimes we need to patch VTK classes, the klass that
    has the methods is different than the klass we want to
    instantiate. get_description_class makes sure that for patched
    classes we get the correct one."""

    try:
        return fix_classes.description[klass]
    except KeyError:
        return klass

parser = VTKMethodParser()


typeMapDict = {'int': Integer,
               'float': Float,
               'char*': String,
               'char *': String,
               'string': String,
               'char': String,
               'const char*': String,
               'const char *': String}
typeMapDictValues = [Integer, Float, String]

file_name_pattern = re.compile('.*FileName$')
set_file_name_pattern = re.compile('Set.*FileName$')

def typeMap(name, package=None):
    """ typeMap(name: str) -> Module
    Convert from C/C++ types into VisTrails Module type
    
    """
    if package is None:
        package = identifier
    if type(name) == tuple:
        return [typeMap(x, package) for x in name]
    if name in typeMapDict:
        return typeMapDict[name]
    else:
        if not registry.has_descriptor_with_name(package, name):
            return None
        else:
            return registry.get_descriptor_by_name(package,
                                                   name).module

def get_method_signature(method):
    """ get_method_signature(method: vtkmethod) -> [ret, arg]
    Re-wrap Prabu's method to increase performance
    
    """
    doc = method.__doc__
    tmp = doc.split('\n')
    sig = []        
    pat = re.compile(r'\b')

    # Remove all the C++ function signatures and V.<method_name> field
    offset = 2+len(method.__name__)
    for i in xrange(len(tmp)):
        s = tmp[i]
        if s=='': break
        if i%2==0:
            x = s.split('->')
            arg = x[0].strip()[offset:]
            if len(x) == 1: # No return value
                ret = None
            else:
                ret = x[1].strip()

            # Remove leading and trailing parens for arguments.
            arg = arg[1:-1]
            if not arg:
                arg = None
            if arg and arg[-1] == ')':
                arg = arg + ','

            # Now quote the args and eval them.  Easy!
            if ret and ret[:3]!='vtk':
                ret = eval(pat.sub('\"', ret))
            if arg:
                if arg.find('(')!=-1:
                    arg = eval(pat.sub('\"', arg))
                else:
                    arg = arg.split(', ')
                    if len(arg)>1:
                        arg = tuple(arg)
                    else:
                        arg = arg[0]
                if type(arg) == str:
                    arg = [arg]

            sig.append(([ret], arg))
    return sig    

def prune_signatures(module, name, signatures, output=False):
    """prune_signatures tries to remove redundant signatures to reduce
    overloading. It _mutates_ the given parameter.

    It does this by performing several operations:

    1) It compares a 'flattened' version of the types
    against the other 'flattened' signatures. If any of them match, we
    keep only the 'flatter' ones.

    A 'flattened' signature is one where parameters are not inside a
    tuple.

    2) We explicitly forbid a few signatures based on modules and names

    """
    # yeah, this is Omega(n^2) on the number of overloads. Who cares?

    def flatten(type_):
        if type_ is None:
            return []
        def convert(entry):
            if type(entry) == tuple:
                return list(entry)
            else:
                assert(type(entry) == str)
                return [entry]
        result = []
        for entry in type_:
            result.extend(convert(entry))
        return result

    flattened_entries = [flatten(sig[1]) for
                         sig in signatures]
    def hit_count(entry):
        result = 0
        for entry in flattened_entries:
            if entry in flattened_entries:
                result += 1
        return result
    hits = [hit_count(entry) for entry in flattened_entries]

    def forbidden(flattened, hit_count, original):
        if (issubclass(get_description_class(module.vtkClass), vtk.vtk3DWidget) and
            name == 'PlaceWidget' and
            flattened == []):
            return True
        # We forbid this because addPorts hardcodes this
        if get_description_class(module.vtkClass) == vtk.vtkAlgorithm:
            return True
        return False

    # This is messy: a signature is only allowed if there's no
    # explicit disallowing of it. Then, if it's not overloaded,
    # it is also allowed. If it is overloaded and not the flattened
    # version, it is pruned. If these are output ports, there can be
    # no parameters.

    def passes(flattened, hit_count, original):
        if forbidden(flattened, hit_count, original):
            return False
        if hit_count == 1:
            return True
        if original[1] is None:
            return True
        if output and len(original[1]) > 0:
            return False
        if hit_count > 1 and len(original[1]) == len(flattened):
            return True
        return False
    
    signatures[:] = [original for (flattened, hit_count, original)
                     in izip(flattened_entries,
                             hits,
                             signatures)
                     if passes(flattened, hit_count, original)]
    
    #then we remove the duplicates, if necessary
    unique_signatures = []
    [unique_signatures.append(s) for s in signatures if not unique_signatures.count(s)]
    signatures[:] = unique_signatures
    
disallowed_classes = set(
    [
    'vtkCriticalSection',
    'vtkDataArraySelection',
    'vtkDebugLeaks',
    'vtkDirectory',
    'vtkDynamicLoader',
    'vtkFunctionParser',
    'vtkGarbageCollector',
    'vtkHeap',
    'vtkInformationKey',
    'vtkInstantiator',
    'vtkLogLookupTable', # VTK: use vtkLookupTable.SetScaleToLog10() instead
    'vtkMath',
    'vtkModelMetadata',
    'vtkMultiProcessController',
    'vtkMutexLock',
    'vtkOutputWindow',
    'vtkPriorityQueue',
    'vtkReferenceCount',
    'vtkRenderWindowCollection',
    'vtkRenderWindowInteractor',
    'vtkTesting',
    'vtkWindow',
     ])

def is_class_allowed(module):
    if module is None:
        return False
    try:
        name = module.__name__
        return not (name in disallowed_classes)
    except AttributeError:
        return True

def addAlgorithmPorts(module):
    """ addAlgorithmPorts(module: Module) -> None
    If module is a subclass of vtkAlgorithm, this function will add all
    SetInputConnection([id],[port]) and GetOutputPort([id]) as
    SetInputConnection{id}([port]) and GetOutputPort{id}.

    """
    if issubclass(get_description_class(module.vtkClass), vtk.vtkAlgorithm):
        if get_description_class(module.vtkClass)!=vtk.vtkStructuredPointsGeometryFilter:
            # We try to instantiate the class here to get the number of
            # ports and to avoid abstract classes
            try:
                instance = module.vtkClass()
            except TypeError:
                pass
            else:
                des = registry.get_descriptor_by_name('edu.utah.sci.vistrails.vtk',
                                                      'vtkAlgorithmOutput')
                for i in xrange(0,instance.GetNumberOfInputPorts()):
                    add_input_port(module, 'SetInputConnection%d'%i, des.module)
                for i in xrange(0,instance.GetNumberOfOutputPorts()):
                    add_output_port(module, 'GetOutputPort%d'%i, des.module)

disallowed_set_get_ports = set(['ReferenceCount',
                                'InputConnection',
                                'OutputPort',
                                'Progress',
                                'ProgressText',
                                'InputArrayToProcess',
                                ])
def addSetGetPorts(module, get_set_dict, delayed):
    """ addSetGetPorts(module: Module, get_set_dict: dict) -> None
    Convert all Setxxx methods of module into input ports and all Getxxx
    methods of module into output ports

    Keyword arguments:
    module       --- Module
    get_set_dict --- the Set/Get method signatures returned by vtk_parser

    """

    klass = get_description_class(module.vtkClass)
    for name in get_set_dict.iterkeys():
        if name in disallowed_set_get_ports: continue
        getterMethod = getattr(klass, 'Get%s'%name)
        setterMethod = getattr(klass, 'Set%s'%name)
        getterSig = get_method_signature(getterMethod)
        setterSig = get_method_signature(setterMethod)
        if len(getterSig) > 1:
            prune_signatures(module, 'Get%s'%name, getterSig, output=True)
        for getter, order in izip(getterSig, xrange(1, len(getterSig)+1)):
            if getter[1]:
                log("Can't handle getter %s (%s) of class %s: Needs input to "
                    "get output" % (order, name, klass))
                continue
            if len(getter[0]) != 1:
                log("Can't handle getter %s (%s) of class %s: More than a "
                    "single output" % (order, name, str(klass)))
                continue
            class_ = typeMap(getter[0][0])
            if is_class_allowed(class_):
                add_output_port(module, 'Get'+name, class_, True)
        if len(setterSig) > 1:
            prune_signatures(module, 'Set%s'%name, setterSig)
        for setter, order in izip(setterSig, xrange(1, len(setterSig)+1)):
            if len(setterSig) == 1:
                n = 'Set' + name
            else:
                n = 'Set' + name + '_' + str(order)
            if len(setter[1]) == 1 and is_class_allowed(typeMap(setter[1][0])):
                add_input_port(module, n,
                               typeMap(setter[1][0]),
                               setter[1][0] in typeMapDict)
            else:
                classes = [typeMap(i) for i in setter[1]]
                if all(classes, is_class_allowed):
                    add_input_port(module, n, classes, True)
            # Wrap SetFileNames for VisTrails file access
            if file_name_pattern.match(name):
                add_input_port(module, 'Set' + name[:-4], 
                               (File, 'input file'), False)
            # Wrap SetRenderWindow for exporters
            elif name == 'RenderWindow':
                # cscheid 2008-07-11 This is messy: VTKCell isn't
                # registered yet, so we can't use it as a port
                # However, we can't register VTKCell before these either,
                # because VTKCell requires vtkRenderer. The "right" way would
                # be to add all modules first, then all ports. However, that would
                # be too slow.
                # Workaround: delay the addition of the port by storing
                # the information in a list
                if registry.has_module('edu.utah.sci.vistrails.spreadsheet',
                                       'SpreadsheetCell'):
                    delayed.add_input_port.append((module, 'SetVTKCell', VTKCell, False))
            # Wrap color methods for VisTrails GUI facilities
            elif name == 'DiffuseColor':
                add_input_port(module, 'SetDiffuseColorWidget',
                               (Color, 'color'), True)
            elif name == 'Color':
                add_input_port(module, 'SetColorWidget', (Color, 'color'),
                               True)
            elif name == 'AmbientColor':
                add_input_port(module, 'SetAmbientColorWidget',
                               (Color, 'color'), True)
            elif name == 'SpecularColor':
                add_input_port(module, 'SetSpecularColorWidget',
                               (Color, 'color'), True)
            elif name == 'EdgeColor':
                add_input_port(module, 'SetEdgeColorWidget',
                               (Color, 'color'), True)

disallowed_toggle_ports = set(['GlobalWarningDisplay',
                               'Debug',
                               ])
def addTogglePorts(module, toggle_dict):
    """ addTogglePorts(module: Module, toggle_dict: dict) -> None
    Convert all xxxOn/Off methods of module into input ports

    Keyword arguments:
    module      --- Module
    toggle_dict --- the Toggle method signatures returned by vtk_parser

    """
    for name in toggle_dict.iterkeys():
        if name in disallowed_toggle_ports:
            continue
        add_input_port(module, name+'On', [], True)
        add_input_port(module, name+'Off', [], True)

disallowed_state_ports = set(['SetInputArrayToProcess'])
def addStatePorts(module, state_dict):
    """ addStatePorts(module: Module, state_dict: dict) -> None
    Convert all SetxxxToyyy methods of module into input ports

    Keyword arguments:
    module     --- Module
    state_dict --- the State method signatures returned by vtk_parser

    """
    klass = get_description_class(module.vtkClass)
    for name in state_dict.iterkeys():
        for mode in state_dict[name]:
            # Creates the port Set foo to bar
            field = 'Set'+name+'To'+mode[0]
            if field in disallowed_state_ports:
                continue
            if not has_input_port(module, field):
                add_input_port(module, field, [], True)

        # Now create the port Set foo with parameter
        if hasattr(klass, 'Set%s'%name):
            setterMethod = getattr(klass, 'Set%s'%name)
            setterSig = get_method_signature(setterMethod)
            # if the signature looks like an enum, we'll skip it, it shouldn't
            # be necessary
            if len(setterSig) > 1:
                prune_signatures(module, 'Set%s'%name, setterSig)
            for ix, setter in enumerate(setterSig):
                if len(setterSig) == 1:
                    n = 'Set' + name
                else:
                    n = 'Set' + name + str(ix+1)
                tm = typeMap(setter[1][0])
                if len(setter[1]) == 1 and is_class_allowed(tm):
                    add_input_port(module, n, tm,
                                   setter[1][0] in typeMapDict)
                else:
                    classes = [typeMap(i) for i in setter[1]]
                    if all(classes, is_class_allowed):
                        add_input_port(module, n, classes, True)

disallowed_other_ports = set(
    [
     'BreakOnError',
     'DeepCopy',
     'FastDelete',
     'HasObserver',
     'HasExecutive',
     'INPUT_ARRAYS_TO_PROCESS',
     'INPUT_CONNECTION',
     'INPUT_IS_OPTIONAL',
     'INPUT_IS_REPEATABLE',
     'INPUT_PORT',
     'INPUT_REQUIRED_DATA_TYPE',
     'INPUT_REQUIRED_FIELDS',
     'InvokeEvent',
     'IsA',
     'Modified',
     'NewInstance',
     'PrintRevisions',
     'RemoveAllInputs',
     'RemoveObserver',
     'RemoveObservers',
     'SafeDownCast',
     'SetInputArrayToProcess',
     'ShallowCopy',
     'Update',
     'UpdateInformation',
     'UpdateProgress',
     'UpdateWholeExtent',
     ])

def addOtherPorts(module, other_list):
    """ addOtherPorts(module: Module, other_list: list) -> None
    Convert all other ports such as Insert/Add.... into input/output

    Keyword arguments:
    module     --- Module
    other_dict --- any other method signatures that is not
                   Algorithm/SetGet/Toggle/State type

    """
    klass = get_description_class(module.vtkClass)
    for name in other_list:
        if name[:3] in ['Add','Set'] or name[:6]=='Insert':
            if name in disallowed_other_ports:
                continue
            method = getattr(klass, name)
            signatures = get_method_signature(method)
            if len(signatures) > 1:
                prune_signatures(module, name, signatures)
            for (ix, sig) in enumerate(signatures):
                ([result], params) = sig
                types = []
                if params:
                    for p in params:
                        t = typeMap(p)
                        if not t:
                            types = None
                            break
                        else: types.append(t)
                else:
                    types = [[]]
                if types:
                    if not all(types, is_class_allowed):
                        continue
                    if len(signatures) == 1:
                        n = name
                    else:
                        n = name + '_' + str(ix+1)
                    if len(types)<=1:
                        add_input_port(module, n, types[0],
                                       types[0] in typeMapDictValues)
                    else:
                        add_input_port(module, n, types, True)
        else:
            if name in disallowed_other_ports:
                continue
            method = getattr(klass, name)
            signatures = get_method_signature(method)
            if len(signatures) > 1:
                prune_signatures(module, name, signatures)
            for (ix, sig) in enumerate(signatures):
                ([result], params) = sig
                types = []
                if params:
                    types = [typeMap(p) for p in params]
                else:
                    types = []
                if not all(types, is_class_allowed):
                    continue
                if types==[] or (result==None):
                    if len(signatures) == 1:
                        n = name
                    else:
                        n = name + '_' + str(ix+1)
                    add_input_port(module, n, types, True)

disallowed_get_ports = set([
    'GetClassName',
    'GetErrorCode',
    'GetNumberOfInputPorts',
    'GetNumberOfOutputPorts',
    'GetOutputPortInformation',
    'GetTotalNumberOfInputConnections',
    ])

def addGetPorts(module, get_list):
    klass = get_description_class(module.vtkClass)
    for name in get_list:
        if name in disallowed_get_ports:
            continue
        method = getattr(klass, name)
        signatures = get_method_signature(method)
        if len(signatures) > 1:
            prune_signatures(module, name, signatures, output=True)
        for ix, getter in enumerate(signatures):
            if getter[1] or len(getter[0]) > 1:
                continue
            class_ = typeMap(getter[0][0])
            if is_class_allowed(class_):
                if len(signatures) > 1:
                    n = name + "_" + str(ix+1)
                else:
                    n = name
                add_output_port(module, n, class_, True)
    
def addPorts(module, delayed):
    """ addPorts(module: VTK module inherited from Module,
                 delayed: object with add_input_port slot
    ) -> None
    
    Search all metamethods of module and add appropriate ports

    ports that cannot be added immediately should be appended to
    the delayed object that is passed. see the SetRenderWindow cases.

    """
    klass = get_description_class(module.vtkClass)
    add_output_port(module, 'self', module)
    parser.parse(klass)
    addAlgorithmPorts(module)
    addGetPorts(module, parser.get_get_methods())
    addSetGetPorts(module, parser.get_get_set_methods(), delayed)
    addTogglePorts(module, parser.get_toggle_methods())
    addStatePorts(module, parser.get_state_methods())
    addOtherPorts(module, parser.get_other_methods())
    # CVS version of VTK doesn't support AddInputConnect(vtkAlgorithmOutput)
    if klass==vtk.vtkAlgorithm:
        add_input_port(module, 'AddInputConnection',
                       typeMap('vtkAlgorithmOutput'))
    # vtkWriters have a custom File port
    elif klass==vtk.vtkWriter:
        add_output_port(module, 'file', typeMap('File',
                                                'edu.utah.sci.vistrails.basic'))
    elif klass==vtk.vtkImageWriter:
        add_output_port(module, 'file', typeMap('File',
                                                'edu.utah.sci.vistrails.basic'))
    elif klass==vtk.vtkVolumeProperty:
        add_input_port(module, 'SetTransferFunction',
                       typeMap('TransferFunction'))
    elif klass==vtk.vtkDataSet:
        add_input_port(module, 'SetPointData', typeMap('vtkPointData'))
        add_input_port(module, 'SetCallData', typeMap('vtkCellData'))
    elif klass==vtk.vtkCell:
        add_input_port(module, 'SetPointIds', typeMap('vtkIdList'))

def setAllPorts(treeNode, delayed):
    """ setAllPorts(treeNode: TreeNode) -> None
    Traverse treeNode and all of its children/grand-children to add all ports

    """
    addPorts(treeNode.descriptor.module, delayed)
    for child in treeNode.children:
        setAllPorts(child, delayed)

def class_dict(base_module, node):
    """class_dict(base_module, node) -> dict
    Returns the class dictionary for the module represented by node and
    with base class base_module"""

    class_dict_ = {}
    def update_dict(name, callable_):
        if class_dict_.has_key(name):
            class_dict_[name] = callable_(class_dict_[name])
        elif hasattr(base_module, name):
            class_dict_[name] = callable_(getattr(base_module, name))
        else:
            class_dict_[name] = callable_(None)

    def guarded_SimpleScalarTree_wrap_compute(old_compute):
        # This builds the scalar tree and makes it cacheable

        def compute(self):
            self.is_cacheable = lambda *args, **kwargs: True
            old_compute(self)
            self.vtkInstance.BuildTree()
        return compute

    def guarded_SetFileName_wrap_compute(old_compute):
        # This checks for the presence of file in VTK readers
        def compute(self):

            # Skips the check if it's a vtkImageReader or vtkPLOT3DReader, because
            # it has other ways of specifying files, like SetFilePrefix for
            # multiple files
            if any([vtk.vtkBYUReader,
                    vtk.vtkImageReader,
                    vtk.vtkPLOT3DReader,
                    vtk.vtkDICOMImageReader,
                    vtk.vtkTIFFReader],
                   lambda x: issubclass(self.vtkClass, x)):
                old_compute(self)
                return
            if self.hasInputFromPort('SetFileName'):
                name = self.getInputFromPort('SetFileName')
            elif self.hasInputFromPort('SetFile'):
                name = self.getInputFromPort('SetFile').name
            else:
                raise ModuleError(self, 'Missing filename')
            if not os.path.isfile(name):
                raise ModuleError(self, 'File does not exist')
            old_compute(self)
        return compute

    def compute_SetDiffuseColorWidget(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetDiffuseColorWidget(self, color):
            self.vtkInstance.SetDiffuseColor(color.tuple)
        return call_SetDiffuseColorWidget

    def compute_SetAmbientColorWidget(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetAmbientColorWidget(self, color):
            self.vtkInstance.SetAmbientColor(color.tuple)
        return call_SetAmbientColorWidget

    def compute_SetSpecularColorWidget(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetSpecularColorWidget(self, color):
            self.vtkInstance.SetSpecularColor(color.tuple)
        return call_SetSpecularColorWidget

    def compute_SetColorWidget(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetColorWidget(self, color):
            self.vtkInstance.SetColor(color.tuple)
        return call_SetColorWidget

    def compute_SetEdgeColorWidget(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetEdgeColorWidget(self, color):
            self.vtkInstance.SetEdgeColor(color.tuple)
        return call_SetEdgeColorWidget

    def compute_SetVTKCell(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetRenderWindow(self, cellObj):
            if cellObj.cellWidget:
                self.vtkInstance.SetRenderWindow(cellObj.cellWidget.mRenWin)
        return call_SetRenderWindow
    
    def compute_SetTransferFunction(old_compute):
        # This sets the transfer function
        if old_compute != None:
            return old_compute
        def call_SetTransferFunction(self, tf):
            tf.set_on_vtk_volume_property(self.vtkInstance)
        return call_SetTransferFunction

    def compute_SetPointData(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetPointData(self, pd):
            self.vtkInstance.GetPointData().ShallowCopy(pd)
        return call_SetPointData

    def compute_SetCellData(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetCellData(self, cd):
            self.vtkInstance.GetCellData().ShallowCopy(cd)
        return call_SetCellData            

    def compute_SetPointIds(old_compute):
        if old_compute != None:
            return old_compute
        def call_SetPointIds(self, point_ids):
            self.vtkInstance.GetPointIds().SetNumberOfIds(point_ids.GetNumberOfIds())
            for i in xrange(point_ids.GetNumberOfIds()):
                self.vtkInstance.GetPointIds().SetId(i, point_ids.GetId(i))
        return call_SetPointIds

    def guarded_Writer_wrap_compute(old_compute):
        # The behavior for vtkWriter subclasses is to call Write()
        # If the user sets a name, we will create a file with that name
        # If not, we will create a temporary file from the file pool
        def compute(self):
            old_compute(self)
            fn = self.vtkInstance.GetFileName()
            if not fn:
                o = self.interpreter.filePool.create_file(suffix='.vtk')
                self.vtkInstance.SetFileName(o.name)
            else:
                o = File()
                o.name = fn
            self.vtkInstance.Write()
            self.setResult('file', o)
        return compute

    for var in dir(node.klass):
        # Everyone that has a Set.*FileName should have a Set.*File port too
        if set_file_name_pattern.match(var):
            def get_compute_SetFile(method_name):
                def compute_SetFile(old_compute):
                    if old_compute != None:
                        return old_compute
                    def call_SetFile(self, file_obj):
                        getattr(self.vtkInstance, method_name)(file_obj.name)
                    return call_SetFile
                return compute_SetFile
            update_dict('_special_input_function_' + var[:-4], 
                        get_compute_SetFile(var))

    if hasattr(node.klass, 'SetFileName'):
        # ... BUT we only want to check existence of filenames on
        # readers. VTK is nice enough to be consistent with names, but
        # this is brittle..
        if node.klass.__name__.endswith('Reader'):
            if not node.klass.__name__.endswith('TiffReader'):
                update_dict('compute', guarded_SetFileName_wrap_compute)
    if hasattr(node.klass, 'SetRenderWindow'):
        update_dict('_special_input_function_SetVTKCell',
                    compute_SetVTKCell)
    #color gui wrapping
    if hasattr(node.klass, 'SetDiffuseColor'):
        update_dict('_special_input_function_SetDiffuseColorWidget',
                    compute_SetDiffuseColorWidget)
    if hasattr(node.klass, 'SetAmbientColor'):
        update_dict('_special_input_function_SetAmbientColorWidget',
                    compute_SetAmbientColorWidget)
    if hasattr(node.klass, 'SetSpecularColor'):
        update_dict('_special_input_function_SetSpecularColorWidget',
                    compute_SetDiffuseColorWidget)
    if hasattr(node.klass, 'SetEdgeColor'):
        update_dict('_special_input_function_SetEdgeColorWidget',
                    compute_SetEdgeColorWidget)
    if hasattr(node.klass, 'SetColor'):
        update_dict('_special_input_function_SetColorWidget',
                    compute_SetColorWidget)
    if issubclass(node.klass, vtk.vtkWriter):
        update_dict('compute', guarded_Writer_wrap_compute)

    if issubclass(node.klass, vtk.vtkScalarTree):
        update_dict('compute', guarded_SimpleScalarTree_wrap_compute)

    if issubclass(node.klass, vtk.vtkVolumeProperty):
        update_dict('_special_input_function_SetTransferFunction',
                    compute_SetTransferFunction)
    if issubclass(node.klass, vtk.vtkDataSet):
        update_dict('_special_input_function_SetPointData',
                    compute_SetPointData)
        update_dict('_special_input_function_SetCellData',
                    compute_SetCellData)
    if issubclass(node.klass, vtk.vtkCell):
        update_dict('_special_input_function_SetPointIds',
                    compute_SetPointIds)
    return class_dict_

disallowed_modules = set([
        'vtkGeoAlignedImageCache',
        'vtkGeoTerrainCache',
        ])
def createModule(baseModule, node):
    """ createModule(baseModule: a Module subclass, node: TreeNode) -> None
    Construct a module inherits baseModule with specification from node
    
    """
    if node.name in disallowed_modules: return
    def obsolete_class_list():
        lst = []
        items = ['vtkInteractorStyleTrackball',
                 'vtkStructuredPointsGeometryFilter',
                 'vtkConstrainedPointHandleRepresentation']
        def try_to_add_item(item):
            try:
                lst.append(getattr(vtk, item))
            except AttributeError:
                pass
        for item in items:
            try_to_add_item(item)
        return lst

    obsolete_list = obsolete_class_list()
    
    def is_abstract():
        """is_abstract tries to instantiate the class. If it's
        abstract, this will raise."""
        # Consider obsolete classes abstract        
        if node.klass in obsolete_list:
            return True
        try:
            getattr(vtk, node.name)()
        except TypeError: # VTK raises type error on abstract classes
            return True
        return False
    module = new_module(baseModule, node.name,
                       class_dict(baseModule, node),
                       docstring=getattr(vtk, node.name).__doc__
                       )

    # This is sitting on the class
    if hasattr(fix_classes, node.klass.__name__ + '_fixed'):
        module.vtkClass = getattr(fix_classes, node.klass.__name__ + '_fixed')
    else:
        module.vtkClass = node.klass
    add_module(module, abstract=is_abstract(), signatureCallable=vtk_hasher)
    for child in node.children:
        if child.name in disallowed_classes:
            continue
        createModule(module, child)

def createAllModules(g):
    """ createAllModules(g: ClassTree) -> None
    Traverse the VTK class tree and add all modules into the module registry
    
    """
    assert len(g.tree[0]) == 1
    base = g.tree[0][0]
    assert base.name == 'vtkObjectBase'
    vtkObjectBase = new_module(vtkBaseModule, 'vtkObjectBase')
    vtkObjectBase.vtkClass = vtk.vtkObjectBase
    add_module(vtkObjectBase)
    for child in base.children:
        if child.name in disallowed_classes:
            continue
        createModule(vtkObjectBase, child)

##############################################################################
# Convenience methods

def extract_vtk_instance(vistrails_obj):
    """extract_vtk_instance(vistrails_obj) -> vtk_object

    takes an instance of a VisTrails module that is a subclass
    of the vtkObjectBase module and returns the corresponding
    instance."""
    vtkObjectBase = registry.getDescriptorByName('vtkObjectBase').module
    assert isinstance(vistrails_obj, vtkObjectBase)
    return vistrails_obj.vtkInstance

def wrap_vtk_instance(vtk_obj):
    """wrap_vtk_instance(vtk_object) -> VisTrails module

    takes a vtk instance and returns a corresponding
    wrapped instance of a VisTrails module"""
    assert isinstance(vtk_obj, vtk.vtkObjectBase)
    m = registry.getDescriptorByName(vtk_obj.GetClassName())
    result = m.module()
    result.vtkInstance = vtk_obj
    return result

################################################################################

def initialize():
    """ initialize() -> None
    Package-entry to initialize the package
    
    """
    # Check VTK version
    v = vtk.vtkVersion()
    version = [v.GetVTKMajorVersion(),
               v.GetVTKMinorVersion(),
               v.GetVTKBuildVersion()]
    if version < [5, 0, 0]:
        raise Exception("You need to upgrade your VTK install to version \
        > >= 5.0.0")
    inheritanceGraph = ClassTree(vtk)
    inheritanceGraph.create()

    # Transfer Function constant
    tf_widget.initialize()

    delayed = InstanceObject(add_input_port=[])
    # Add VTK modules
    add_module(vtkBaseModule)
    createAllModules(inheritanceGraph)
    setAllPorts(registry.get_tree_node_from_name(identifier,
                                                 'vtkObjectBase'),
                delayed)

    # Register the VTKCell and VTKHandler type if the spreadsheet is up
    if registry.has_module('edu.utah.sci.vistrails.spreadsheet',
                           'SpreadsheetCell'):
        import vtkhandler
        import vtkcell
        vtkhandler.registerSelf()
        vtkcell.registerSelf()

    # register offscreen rendering module
    offscreen.register_self()

    # Now add all "delayed" ports - see comment on addSetGetPorts
    for args in delayed.add_input_port:
        
        add_input_port(*args)

    # register Transfer Function adjustment
    # This can't be reordered -- TransferFunction needs to go before
    # vtkVolumeProperty, but vtkScaledTransferFunction needs
    # to go after vtkAlgorithmOutput
    
    add_module(tf_widget.vtkScaledTransferFunction)
    add_input_port(tf_widget.vtkScaledTransferFunction,
                   'Input',
                   registry.get_descriptor_by_name('edu.utah.sci.vistrails.vtk',
                                                   'vtkAlgorithmOutput').module)
    add_input_port(tf_widget.vtkScaledTransferFunction,
                   'Dataset',
                   registry.get_descriptor_by_name('edu.utah.sci.vistrails.vtk',
                                                   'vtkDataObject').module)
    add_input_port(tf_widget.vtkScaledTransferFunction,
                   'Range',
                   [Float, Float])
    add_input_port(tf_widget.vtkScaledTransferFunction,
                   'TransferFunction',
                   tf_widget.TransferFunctionConstant)
    add_output_port(tf_widget.vtkScaledTransferFunction,
                    'TransferFunction',
                    tf_widget.TransferFunctionConstant)

    inspectors.initialize()

def package_dependencies():
    import core.packagemanager
    manager = core.packagemanager.get_package_manager()
    if manager.has_package('edu.utah.sci.vistrails.spreadsheet'):
        return ['edu.utah.sci.vistrails.spreadsheet']
    else:
        return []

def package_requirements():
    import core.requirements
    if not core.requirements.python_module_exists('vtk'):
        raise core.requirements.MissingRequirement('vtk')
    if not core.requirements.python_module_exists('PyQt4'):
        print 'PyQt4 is not available. There will be no interaction',
        print 'between VTK and the spreadsheet.'
    import vtk


################################################################################

# Commenting out because we no longer have a vtkRenderWindow module..

# from core.console_mode import run
# import os
# import core.system
# import unittest
# from core.db.locator import XMLFileLocator

# class TestVTKPackage(unittest.TestCase):

#     def test_writer(self):

#         result_filename = (core.system.temporary_directory() +
#                            os.path.sep +
#                            'test_vtk_12345.vtk')
#         template_filename = (core.system.vistrails_root_directory() +
#                              '/tests/resources/vtkfiles/vtk_quadric_writer_test.vtk')

#         def compare():
#             for (l1, l2) in izip(file(result_filename, 'r'),
#                                  file(template_filename, 'r')):
#                 if l1 != l2:
#                     self.fail("Resulting file doesn't match template")
            
#         locator = XMLFileLocator(core.system.vistrails_root_directory() +
#                                  '/tests/resources/vtk.xml')

#         result = run(locator, "writer_test")
#         self.assertEquals(result, True)
#         compare()
#         os.remove(result_filename)

#         result = run(locator, "writer_test_filesink")
#         self.assertEquals(result, True)
#         compare()
#         os.remove(result_filename)
        
