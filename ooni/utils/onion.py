#
# onion.py
# ----------
# Utilities for working with Tor.
#
# This code is largely taken from txtorcon and its documentation, and as such
# any and all credit should go to Meejah. Minor adjustments have been made to
# use OONI's logging system, and to build custom circuits without actually
# attaching streams.
#
# :author: Meejah, Isis Lovecruft
# :license: see included LICENSE file
# :copyright: copyright (c) 2012 The Tor Project, Inc.
# :version: 0.1.0-alpha
#

import random

from ooni.lib.txtorcon import CircuitListenerMixin, IStreamAttacher
from ooni.utils        import log
from zope.interface    import implements


def __setup_done__(proto):
    log.msg("Setup Complete: %s" % proto)
    state = TorState(proto.tor_protocol)
    state.post_bootstrap.addCallback(__state_complete__)
    state.post_bootstrap.addErrback(__setup_fail__)

def __setup_fail__(proto):
    log.err("Setup Failed: %s" % proto)
    report.update({'setup_fail': proto})
    reactor.stop()

def __state_complete__(state, bridge_list=None, relay_list=None):
    """Called when we've got a TorState."""
    log.msg("We've completely booted up a Tor version %s at PID %d"
            % (state.protocol.version, state.tor_pid))

    log.msg("This Tor has the following %d Circuits:"
            % len(state.circuits))
    for circ in state.circuits.values():
        log.msg("%s" % circ)

    if bridge_list is not None and relay_list is None:
        return state, bridge_list
    elif bridge_list is None and relay_list is not None:
        raise NotImplemented
    else:
        return state, None

def __updates__(_progress, _tag, _summary):
    log.msg("%d%%: %s", _progress, _summary)

def write_torrc(conf, data_dir=None):
    """
    Create a torrc in our data_dir. If we don't yet have a data_dir, create a
    temporary one. Any temporary files or folders are added to delete_list.
    
    :return: torrc, data_dir, delete_list
    """
    try:
        from os       import write, close
        from tempfile import mkstemp, mkdtemp
    except ImportError, ie:
        log.err(ie)

    delete_list = []
    
    if data_dir is None:
        data_dir = mkdtemp(prefix='bridget-tordata')
        delete_list.append(data_dir)
    conf.DataDirectory = data_dir
    
    (fd, torrc) = mkstemp(dir=data_dir)
    delete_list.append(torrc)
    write(fd, conf.create_torrc())
    close(fd)
    return torrc, data_dir, delete_list

def delete_files_or_dirs(delete_list):
    """
    Given a list of files or directories to delete, delete all and suppress
    all errors.

    :param delete_list:
        A list of files or directories to delete.
    """
    try:
        from os     import unlink
        from shutil import rmtree
    except ImportError, ie:
        log.err(ie)

    for temp in delete_list:
        try:
            unlink(temp)
        except OSError:
            rmtree(temp, ignore_errors=True)

def start_tor(reactor, config, control_port, tor_binary, data_dir,
              report=None, progress=__updates__, process_cb=__setup_done__,
              process_eb=__setup_fail__):
    """
    Use a txtorcon.TorConfig() instance, config, to write a torrc to a
    tempfile in our DataDirectory, data_dir. If data_dir is None, a temp
    directory will be created. Finally, create a TCP4ClientEndpoint at our
    control_port, and connect it to our reactor and a spawned Tor
    process. Compare with :meth:`txtorcon.launch_tor` for differences.

    :param reactor:
        An instance of class:`twisted.internet.reactor`.
    :param config:
        An instance of class:`txtorcon.TorConfig` with all torrc options
        already configured. ivar:`config.ControlPort`,
        ivar:`config.SocksPort`, ivar:`config.CookieAuthentication`, should
        already be set, as well as ivar:`config.UseBridges` and
        ivar:`config.Bridge` if bridges are to be used.
        ivar:`txtorcon.DataDirectory` does not need to be set.
    :param control_port:
        The port number to use for Tor's ControlPort.
    :param tor_binary:
        The full path to the Tor binary to use.
    :param data_dir:
        The directory to use as Tor's DataDirectory.
    :param report:
        The class:`ooni.plugoo.reports.Report` instance to .update().
    :param progress:
        A non-blocking function to handle bootstrapping updates, which takes
        three parameters: _progress, _tag, and _summary.
    :param process_cb:
        The function to callback to after 
        class:`ooni.lib.txtorcon.TorProcessProtocol` returns with the fully
        bootstrapped Tor process.
    :param process_eb:
        The function to errback to if 
        class:`ooni.lib.txtorcon.TorProcessProtocol` fails.
    :return:
        A class:`ooni.lib.txtorcon.TorProcessProtocol` which callbacks with a
        class:`txtorcon.TorControlProtocol` as .protocol.
    """
    try:
        from functools                  import partial
        from twisted.internet.endpoints import TCP4ClientEndpoint
        from ooni.lib.txtorcon          import TorProtocolFactory
        from ooni.lib.txtorcon          import TorProcessProtocol
    except ImportError, ie:
        log.err(ie)

    ## TODO: add option to specify an already existing torrc, which
    ##       will require prior parsing to enforce necessary lines
    (torrc, data_dir, to_delete) = write_torrc(config, data_dir)

    log.msg("Starting Tor ...")
    log.msg("Using the following as our torrc:\n%s" % config.create_torrc())
    if report is None:
        report = {'torrc': config.create_torrc()}
    else:
        report.update({'torrc': config.create_torrc()})

    end_point = TCP4ClientEndpoint(reactor, 'localhost', control_port)
    connection_creator = partial(end_point.connect, TorProtocolFactory())
    process_protocol = TorProcessProtocol(connection_creator, progress)
    process_protocol.to_delete = to_delete
    process_protocol.addCallback(process_cb)
    process_protocol.addErrback(process_eb)

    reactor.addSystemEventTrigger('before', 'shutdown',
                                  partial(delete_files_or_dirs, to_delete))
    try:
        transport = reactor.spawnProcess(process_protocol,
                                         tor_binary,
                                         args=(tor_binary,'-f',torrc),
                                         env={'HOME': data_dir},
                                         path=data_dir)
        transport.closeStdin()
    except RuntimeError as e:
        log.err("Starting Tor failed: %s" % e)
        process_protocol.connected_cb.errback(e)
    except NotImplementedError, e:
        url = "http://starship.python.net/crew/mhammond/win32/Downloads.html"
        log.err("Running bridget on Windows requires pywin32: %s" % url)
        process_protocol.connected_cb.errback(e)

    return process_protocol.connected_cb     ## new defer.Deferred()
    

class CustomCircuit(CircuitListenerMixin):
    implements(IStreamAttacher)

    def __init__(self, state, relays=None):
        self.state = state
        self.waiting_circuits = []
        self.relays = relays

    def waiting_on(self, circuit):
        for (circid, d) in self.waiting_circuits:
            if circuit.id == circid:
                return True
        return False

    def circuit_extend(self, circuit, router):
        "ICircuitListener"
        if circuit.purpose != 'GENERAL':
            return
        if self.waiting_on(circuit):
            log.msg("Circuit %d (%s)" % (circuit.id, router.id_hex))

    def circuit_built(self, circuit):
        "ICircuitListener"
        if circuit.purpose != 'GENERAL':
            return
        log.msg("Circuit %s built ..." % circuit.id)
        log.msg("Full path of %s: %s" % (circuit.id, circuit.path))
        for (circid, d) in self.waiting_circuits:
            if circid == circuit.id:
                self.waiting_circuits.remove((circid, d))
                d.callback(circuit)

    def circuit_failed(self, circuit, reason):
        if self.waiting_on(circuit):
            log.msg("Circuit %s failed for reason %s" % (circuit.id, reason))
            circid, d = None, None
            for c in self.waiting_circuits:
                if c[0] == circuit.id:
                    circid, d = c
            if d is None:
                raise Exception("Expected to find circuit.")

            self.waiting_circuits.remove((circid, d))
            log.msg("Trying to build a circuit for %s" % circid)
            self.request_circuit_build(d)

    def check_circuit_route(self, router):
        """
        Check if a relay is a hop in one of our already built circuits. 

        """
        for circ in self.state.circuits.values():
            if router in circuit.path:
            #router.update() ## XXX can i use without args? no.
                TorInfo.dump(self)

    def request_circuit_build(self, deferred, path=None):
        if path is None:
            if self.state.relays_remaining() > 0:
                first, middle,last = (self.state.relays.pop()
                                      for i in range(3))
            else:
                first = random.choice(self.state.entry_guards.values())
                middle, last = (random.choice(self.state.routers.values())
                                for i in range(2))
            path = [first, middle, last]
        else:
            assert type(path) is list, "Circuit path must be a list of relays!"
            assert len(path) >= 3, "Circuits must be at least three hops!"

        log.msg("Requesting a circuit: %s" 
                % '->'.join(map(lambda node: node, path)))

        class AppendWaiting:
            def __init__(self, attacher, deferred):
                self.attacher = attacher
                self.d        = deferred
            def __call__(self, circ):
                """
                Return from build_circuit is a Circuit, however,
                we want to wait until it is built before we can
                issue an attach on it and callback to the Deferred
                we issue here.
                """
                log.msg("Circuit %s is in progress ..." % circ.id)
                self.attacher.waiting_circuits.append((circ.id, self.d))

        return self.state.build_circuit(path).addCallback(
            AppendWaiting(self, deferred)).addErrback(
            log.err)