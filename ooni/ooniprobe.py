#!/usr/bin/env python
# -*- coding: UTF-8
#
#    ooniprobe
#    *********
#
#    Open Observatory of Network Interference
#
#    "The Net interprets censorship as damage and routes around it."
#                    - John Gilmore; TIME magazine (6 December 1993)
#
#    The goal of ooni-probe is to collect data about censorship around
#    the world.
#
#    :copyright: (c) 2012 by Arturo Filastò, Isis Lovecruft
#    :license: see LICENSE for more details.
#    :version: 0.0.1-pre-alpha
#

import sys
from pprint import pprint

from twisted.python import usage
from twisted.internet import reactor
from twisted.plugin import getPlugins

from zope.interface.verify import verifyObject
from zope.interface.exceptions import BrokenImplementation
from zope.interface.exceptions import BrokenMethodImplementation

from plugoo import tests, work, assets, reports
from plugoo.interface import ITest
from utils.logo import getlogo
from utils import log
import plugins

__version__ = "0.0.1-prealpha"

def retrieve_plugoo():
    """
    Get all the plugins that implement the ITest interface and get the data
    associated to them into a dict.
    """
    interface = ITest
    d = {}
    error = False
    for p in getPlugins(interface, plugins):
        try:
            verifyObject(interface, p)
            d[p.shortName] = p
        except BrokenImplementation, bi:
            print "Plugin Broken"
            print bi
            error = True
    if error != False:
        print "Plugin Loaded!"
    return d

plugoo = retrieve_plugoo()

def runTest(test, options, global_options, reactor=reactor):
    """
    Run an OONI probe test by name.

    @param test: a string specifying the test name as specified inside of
                 shortName.

    @param options: the local options to be passed to the test.

    @param global_options: the global options for OONI
    """
    parallelism = int(global_options['parallelism'])
    worker = work.Worker(parallelism, reactor=reactor)
    test_class = plugoo[test].__class__
    report = reports.Report(test, global_options['output'])

    log_to_stdout = True
    if global_options['quiet']:
        log_to_stdout = False

    log.start(log_to_stdout,
              global_options['log'],
              global_options['verbosity'])

    resume = 0
    if not options:
        options = {}
    if 'resume' in options:
        resume = options['resume']

    test = test_class(options, global_options, report, reactor=reactor)
    if test.tool:
        test.runTool()
        return True

    if test.ended:
        print "Ending test"
        return None

    wgen = work.WorkGenerator(test,
                              dict(options),
                              start=resume)
    for x in wgen:
        worker.push(x)

    return True

class Options(usage.Options):
    tests = plugoo.keys()
    subCommands = []
    for test in tests:
        subCommands.append([test, None, plugoo[test].options, "Run the %s test" % test])

    optFlags = [
        #['remote', 'r', "If the test should be run remotely (not supported)"],
        #['status', 'x', 'Show current state'],
        #['restart', 'r', 'Restart OONI'],
        ['quiet', 'q', "Don't log to stdout"]
    ]

    optParameters = [
        ['parallelism', 'n', 10, "Specify the number of parallel tests to run"],
        #['target-node', 't', 'localhost:31415', 'Select target node'],
        ['output', 'o', 'report.log', "Specify output report file"],
        ['log', 'l', 'oonicli.log', "Specify output log file"],
        ['verbosity', 'v', 1, "Specify the logging level"],
        #['password', 'p', 'opennetwork', "Specify the password for authentication"],
    ]

    def opt_version(self):
        """
        Display OONI version and exit.
        """
        print "OONI version:", __version__
        sys.exit(0)

    def __str__(self):
        """
        Hack to get the sweet ascii art into the help output and replace the
        strings "Commands" with "Tests".
        """
        return getlogo() + '\n' + self.getSynopsis() + '\n' + \
               self.getUsage(width=None).replace("Commands:", "Tests:")

if __name__ == "__main__":
    config = Options()
    config.parseOptions()

    if not config.subCommand:
        #print "Error! No Test Specified."
        config.opt_help()
        sys.exit(1)

    if runTest(config.subCommand, config.subOptions, config):
        reactor.run()

