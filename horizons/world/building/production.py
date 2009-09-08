# ###################################################
# Copyright (C) 2009 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

import horizons.main

from horizons.world.building.collectingproducerbuilding import CollectingProducerBuilding
from horizons.world.production.producer import ProducerBuilding
from horizons.gui.tabs import TabWidget, InventoryTab, ProductionOverviewTab
from horizons.util import Point
from building import BasicBuilding, SelectableBuilding
from buildable import BuildableSingle, BuildableSingleOnCoast
from horizons.constants import UNITS
from horizons.entities import Entities


class Farm(SelectableBuilding, CollectingProducerBuilding, BuildableSingle, BasicBuilding):
	pass

""" AnimalFarm is not used for now

class AnimalFarm(SelectableBuilding, CollectingProducerBuilding, BuildableSingleWithSurrounding, BasicBuilding):
	_surroundingBuildingClass = 18
	"" This class builds pasturage in the radius automatically,
	so that farm animals can graze there ""

	def __init__(self, **kwargs):
		super(AnimalFarm, self).__init__(**kwargs)

	def create_collector(self):
		self.animals = []

		# NOTE: animals have to be created before the AnimalCollector
		for (animal, number) in horizons.main.db("SELECT unit_id, count FROM data.animals \
		                                    WHERE building_id = ?", self.id):
			for i in xrange(0, number):
				Entities.units[animal](self)

		super(AnimalFarm, self).create_collector()

	def save(self, db):
		super(AnimalFarm, self).save(db)
		for animal in self.animals:
			animal.save(db)

	def load(self, db, worldid):
		super(AnimalFarm, self).load(db, worldid)
		self.animals = []

	def remove(self):
		while len(self.animals) > 0:
			self.animals[0].remove()
		super(AnimalFarm, self).remove()
"""


class Lumberjack(SelectableBuilding, CollectingProducerBuilding, BuildableSingle, BasicBuilding):
	pass

class Weaver(SelectableBuilding, CollectingProducerBuilding, BuildableSingle, BasicBuilding):
	pass

class Hunter(SelectableBuilding, CollectingProducerBuilding, BuildableSingle, BasicBuilding):
	pass

class Fisher(SelectableBuilding, ProducerBuilding, BuildableSingleOnCoast, BasicBuilding):
	pass

class Church(SelectableBuilding, ProducerBuilding, BuildableSingle, BasicBuilding):
	tabs=[ProductionOverviewTab] # don't show inventory, just production (i.e. running costs)