# Copyright (C) 2008 Ross Burton <ross@burtonini.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51 Franklin
# St, Fifth Floor, Boston, MA 02110-1301 USA


import gobject

import logging
logger = logging.getLogger("Context")

# TODO: make running leave on startup optional
# TODO: add flag for "silent" so that context changes are not announced

class Context(gobject.GObject):

    __gsignals__ = {
        'changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }
    
    def __init__(self, name):
        gobject.GObject.__init__(self)
        self.name = name
        self.rules = []
        self.entering_actions = []
        self.leaving_actions = []
    
    def getName(self):
        return self.name

    def addRule(self, rule):
        def changed(source):
            self.emit("changed")
        rule.source.connect("changed", changed)
        self.rules.append(rule)

    def addEnterAction(self, action):
        self.entering_actions.append(action)

    def addLeaveAction(self, action):
        self.leaving_actions.append(action)

    def runEnteringActions(self):
        logger.info ("Entering %s" % self)
        for a in self.entering_actions:
            try:
                a.run()
            except Exception, e:
                logger.warning("Cannot enter %s: %s" % (self, e))

    def runLeavingActions(self):
        logger.info ("Leaving %s" % self)
        for a in self.leaving_actions:
            try:
                a.run()
            except Exception, e:
                logger.warning("Cannot leave %s: %s" % (self, e))

    def evaluateRules(self):
        # TODO: Provide other ways to evaluate rules with OR and AND? Let's have
        # only AND for now.  Maybe add "confidence" to the rules, which can be
        # use to implement this.

        # Handle no rules specially
        if not self.rules:
            return False

        for r in self.rules:
            if not r.evaluate():
                return False
        return True 

    def getPollInterval(self):
        intervals = [r.source.getPollInterval() for r in self.rules if r.source.getPollInterval()]
        if intervals:
            return min(intervals)
        else:
            return 0

    def __str__(self):
        return self.name

gobject.type_register(Context)
