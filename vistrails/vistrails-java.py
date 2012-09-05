###############################################################################
##
## Copyright (C) 2006-2011, University of Utah. 
## All rights reserved.
## Contact: contact@vistrails.org
##
## This file is part of VisTrails.
##
## "Redistribution and use in source and binary forms, with or without 
## modification, are permitted provided that the following conditions are met:
##
##  - Redistributions of source code must retain the above copyright notice, 
##    this list of conditions and the following disclaimer.
##  - Redistributions in binary form must reproduce the above copyright 
##    notice, this list of conditions and the following disclaimer in the 
##    documentation and/or other materials provided with the distribution.
##  - Neither the name of the University of Utah nor the names of its 
##    contributors may be used to endorse or promote products derived from 
##    this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" 
## AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, 
## THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR 
## PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR 
## CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, 
## EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, 
## PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; 
## OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, 
## WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR 
## OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF 
## ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
##
###############################################################################
"""Alternate main file for the VisTrails distribution that uses Java."""

if __name__ == '__main__':
    import core.system
    core.system.set_configuration_suffix('java')

    from core import debug

    try:
        import PyQt4
    except ImportError:
        from sys import stderr
        stderr.write("Unable to import PyQt4!\n"
                     "While this shouldn't be necessary in order to run the "
                     "Jython version of\nVistrails, based on Swing, there "
                     "are still a lot of import dependencies on\nunavailable "
                     "modules.\nYou might want to download the stub modules:\n"
                     "  http://dl.dropbox.com/u/13131521/"
                     "jython-fake-site-packages.zip\n"
                     "and extract them in your jython/Lib/site-packages "
                     "directory.\n\n")

    import javagui.application
    import sys
    import os
    try:
        v = javagui.application.start_application()
        if v != 0:
            app = javagui.application.get_vistrails_application()
            if app:
                app.finishSession()
            sys.exit(v)
        app = javagui.application.get_vistrails_application()
    except SystemExit, e:
        app = javagui.application.get_vistrails_application()
        if app:
            app.finishSession()
        sys.exit(e)
    except Exception, e:
        app = javagui.application.get_vistrails_application()
        if app:
            app.finishSession()
        print "Uncaught exception on initialization: %s" % e
        import traceback
        traceback.print_exc()
        sys.exit(255)

    v = app.wait_finish()
    sys.exit(v)