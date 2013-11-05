import copy
from itertools import izip
import time

from vistrails.core.modules.vistrails_module import Module, InvalidOutput, \
    ModuleError, ModuleConnector

from fold import create_constant


class While(Module):
    """
    The While Module runs a module over and over until the condition port
    is false. Then, it returns the result.
    """

    def __init__(self):
        Module.__init__(self)
        self.is_looping_module = True

    def update(self):
        self.logging.begin_update(self)

        if len(self.inputPorts.get('FunctionPort', [])) != 1:
            raise ModuleError(self,
                              "%s module should have exactly one connection "
                              "on its FunctionPort" % self.__class__.__name__)
        self.updateUpstream(
                self.other_ports_ready,
                [n for n in self.inputPorts.iterkeys() if n != 'FunctionPort'])

    def other_ports_ready(self, connectors):
        """Starts looping once upstream modules are done (except the loop).
        """
        for port_name, connectorList in copy.copy(self.inputPorts.items()):
            if port_name != 'FunctionPort':
                for connector in connectorList:
                    mod, port = connector.obj, connector.port
                    if mod.get_output(port) is InvalidOutput:
                        self.removeInputConnector(port_name, connector)

        self.name_output = self.getInputFromPort('OutputPort')
        self.name_condition = self.forceGetInputFromPort('ConditionPort')
        self.name_state_input = self.forceGetInputFromPort('StateInputPorts')
        self.name_state_output = self.forceGetInputFromPort('StateOutputPorts')
        self.max_iterations = self.getInputFromPort('MaxIterations')
        self.delay = self.forceGetInputFromPort('Delay')

        if (self.name_condition is None and
                not self.hasInputFromPort('MaxIterations')):
            raise ModuleError(self,
                              "Please set MaxIterations or use ConditionPort")

        if self.name_state_input or self.name_state_output:
            if not self.name_state_input or not self.name_state_output:
                raise ModuleError(self,
                                  "Passing state between iterations requires "
                                  "BOTH StateInputPorts and StateOutputPorts "
                                  "to be set")
            if len(self.name_state_input) != len(self.name_state_output):
                raise ModuleError(self,
                                  "StateInputPorts and StateOutputPorts need "
                                  "to have the same number of ports "
                                  "(got %d and %d)" % (
                                  len(self.name_state_input),
                                  len(self.name_state_output)))

        connectors = self.inputPorts.get('FunctionPort')
        if len(connectors) != 1:
            raise ModuleError(self,
                              "Multiple modules connected on FunctionPort")
        self.orig_module = connectors[0].obj

        self.logging.begin_compute(self)
        self.iteration(0, None)

    def iteration(self, i, state):
        """Starts one iteration of the loop.
        """
        module = copy.copy(self.orig_module)

        if not self.upToDate:
            module.upToDate = False
            module.computed = False

            # For logging
            module.is_looping = True
            module.first_iteration = i == 0
            module.last_iteration = False
            module.loop_iteration = i

            # Set state on input ports
            if i > 0 and self.name_state_input:
                for value, port in izip(state, self.name_state_input):
                    if port in module.inputPorts:
                        del module.inputPorts[port]
                    new_connector = ModuleConnector(
                            create_constant(value),
                            'value')
                    module.set_input_port(port, new_connector)

        self.run_upstream_module(lambda: self.iteration_done(i, module),
                                 module)

    def iteration_done(self, i, module):
        """Finishes or starts a new iteration.
        """
        if self.name_condition is not None:
            if self.name_condition not in module.outputPorts:
                raise ModuleError(
                        self.orig_module,
                        "Invalid output port: %s" % self.name_condition)
            if not module.get_output(self.name_condition):
                self.finished(module)
                return

        if self.delay:
            # TODO : how do I do that? need to start a delayer thread...
            pass

        # Get state on output ports
        if self.name_state_output:
            state = [module.get_output(port)
                     for port in self.name_state_output]

        if i + 1 >= self.max_iterations:
            self.finished(module)
        else:
            self.iteration(i + 1, state)

    def finished(self, module):
        """Execution done, set result.
        """
        if self.name_output not in module.outputPorts:
            raise ModuleError(self.orig_module,
                              "Invalid output port: %s" % self.name_output)
        result = module.get_output(self.name_output)
        self.setResult('Result', result)

        self.logging.end_update(self)
        self.logging.signalSuccess(self)
        self.done()


###############################################################################

import unittest

class TestWhile(unittest.TestCase):
    def test_pythonsource(self):
        import urllib2
        source = ('o = i * 2\n'
                  "r = \"it's %d!!!\" % o\n"
                  'go_on = o < 100')
        source = urllib2.quote(source)
        from vistrails.tests.utils import execute, intercept_result
        with intercept_result(While, 'Result') as results:
            self.assertFalse(execute([
                    ('PythonSource', 'org.vistrails.vistrails.basic', [
                        ('source', [('String', source)]),
                        ('i', [('Integer', '5')]),
                    ]),
                    ('While', 'org.vistrails.vistrails.control_flow', [
                        ('ConditionPort', [('String', 'go_on')]),
                        ('OutputPort', [('String', 'r')]),
                        ('StateInputPorts', [('List', "['i']")]),
                        ('StateOutputPorts', [('List', "['o']")]),
                    ]),
                ],
                [
                    (0, 'self', 1, 'FunctionPort'),
                ],
                add_port_specs=[
                    (0, 'input', 'i',
                     'org.vistrails.vistrails.basic:Integer'),
                    (0, 'output', 'o',
                     'org.vistrails.vistrails.basic:Integer'),
                    (0, 'output', 'r',
                     'org.vistrails.vistrails.basic:String'),
                    (0, 'output', 'go_on',
                     'org.vistrails.vistrails.basic:Boolean'),
                ]))
        self.assertEqual(results, ["it's 160!!!"])
