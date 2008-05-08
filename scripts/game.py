# ###################################################
# Copyright (C) 2008 The OpenAnnoTeam
# team@openanno.org
# This file is part of OpenAnno.
#
# OpenAnno is free software; you can redistribute it and/or modify
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
import math
import fife
import pychan
from eventlistenerbase import EventListenerBase
from units.ship import Ship
from units.house import House
from player import Player
from dbreader import DbReader
from ingamegui import IngameGui
from island import Island
import timermanager
from settlement import Settlement

_MODE_COMMAND, _MODE_BUILD = xrange(2)

class Game(EventListenerBase):
    """Game class represents the games main ingame view and controls cameras and map loading."""

    def __init__(self, main, map):
        """@var main: parant Openanno instance
        @var map: string with the mapfile path
        """
        self.main = main
        engine = self.main.engine
        super(Game, self).__init__(engine, regMouse=True, regKeys=True)

        #
        # Engine specific variables
        #
        self.engine = engine
        self.eventmanager = engine.getEventManager()
        self.model = engine.getModel()
        self.metamodel = self.model.getMetaModel()

        #
        # Map and Instance specific variables
        #
        self.island_uid = 0     # Unique id used for islands.
        self.islands = {}
        self.uid = 0            # Unique id used to create unique ids for instances.
        self.layers = {}
        self.selected_instance = None
        self.instance_to_unit = {}

        #
        # Player related variables
        #
        self.human_player = None
        self.players = {}

        #
        # Camera related variables
        #
        self.cam = None         # Main camera
        self.overview = None    # Overview camera
        self.view = None
        self.outline_renderer = None

        #
        # Gui related variables
        #
        self.ingame_gui = None

        #
        # Other variables
        #
        self.mode = _MODE_COMMAND
        self.timermanager = timermanager.TimerManager() # Manages timers

        #
        # _MODE_BUILD variables
        #
        self._build_tiles = None    # Stores the area a building can be built on  

        #
        # Beginn map creation
        #
        self.loadmap(map)
        self.creategame()

    def __del__(self):
        super(Game, self).__del__()
        self.model.deleteMap(self.map)
        self.metamodel.deleteDatasets()
        self.view.clearCameras()
        self.timermanager.stop_all()

    def loadmap(self, map):
        """Loads a map.
        @var map: string with the mapfile path.
        """
        self.main.db.query("attach ? as map", (map))
        self.map = self.model.createMap("map")

        self.datasets = {}
        #dataset for ground tiles
        self.datasets['ground']=self.metamodel.createDataset("ground")
        #dataset for objects
        self.datasets['building']=self.metamodel.createDataset("building")

        self.create_object("blocker", "content/gfx/dummies/transparent.png", "content/gfx/dummies/transparent.png", "content/gfx/dummies/transparent.png", "content/gfx/dummies/transparent.png", "content/gfx/dummies/transparent.png", self.datasets['ground'])
        #todo...
        for (oid, multi_action_or_animated) in self.main.db.query("SELECT id, max(actions_and_images) > 1 AS multi_action_or_animated FROM ( SELECT ground.oid as id, action.animation as animation, count(*) as actions_and_images FROM ground LEFT JOIN action ON action.ground = ground.oid LEFT JOIN animation ON action.animation = animation.animation_id GROUP BY ground.oid, action.rotation ) x GROUP BY id").rows:
            print oid, multi_action_or_animated

        for (oid, image_overview, image_n, image_e, image_s, image_w) in self.main.db.query("select gnd.oid, grp.image_overview, (select file from data.animation where animation_id = (select animation from data.action where ground = gnd.rowid and rotation = 45) order by frame_end limit 1) as image_n, (select file from data.animation where animation_id = (select animation from data.action where ground = gnd.rowid and rotation = 135) order by frame_end limit 1) as image_e, (select file from data.animation where animation_id = (select animation from data.action where ground = gnd.rowid and rotation = 225) order by frame_end limit 1) as image_s, (select file from data.animation where animation_id = (select animation from data.action where ground = gnd.rowid and rotation = 315) order by frame_end limit 1) as image_w from data.ground gnd left join data.ground_group grp on gnd.`group` = grp.oid").rows:
            self.create_object(oid, image_overview, image_n, image_e, image_s, image_w, self.datasets['ground'])

        for (oid, image_overview, image_n, image_e, image_s, image_w, size_x, size_y) in self.main.db.query("select oid, 'content/gfx/dummies/overview/object.png', (select file from data.animation where animation_id = (select animation from data.action where object = data.building.rowid and rotation = 45) order by frame_end limit 1) as image_n, (select file from data.animation where animation_id = (select animation from data.action where object = data.building.rowid and rotation = 135) order by frame_end limit 1) as image_e, (select file from data.animation where animation_id = (select animation from data.action where object = data.building.rowid and rotation = 225) order by frame_end limit 1) as image_s, (select file from data.animation where animation_id = (select animation from data.action where object = data.building.rowid and rotation = 315) order by frame_end limit 1) as image_w, size_x, size_y from data.building").rows:
            self.create_object(oid, image_overview, image_n, image_e, image_s, image_w, self.datasets['building'], size_x, size_y)

        cellgrid = fife.SquareGrid(False)
        cellgrid.thisown = 0
        cellgrid.setRotation(0)
        cellgrid.setXScale(1)
        cellgrid.setYScale(1)
        cellgrid.setXShift(0)
        cellgrid.setYShift(0)

        self.layers['water'] = self.map.createLayer("layer1", cellgrid)
        self.layers['land'] = self.map.createLayer("layer2", cellgrid)
        self.layers['units'] = self.map.createLayer("layer3", cellgrid)
        self.layers['units'].setPathingStrategy(fife.CELL_EDGES_ONLY)

        min_x, min_y, max_x, max_y = 0, 0, 0, 0
        for (island, offset_x, offset_y) in self.main.db.query("select island, x, y from map.islands").rows:
            self.main.db.query("attach ? as island", (str(island)))
            self.islands[self.island_uid]=Island(self.island_uid)
            cur_isl = self.islands[self.island_uid]
            for (x, y, ground, layer) in self.main.db.query("select i.x, i.y, i.ground_id, g.ground_type_id from island.ground i left join data.ground c on c.oid = i.ground_id left join data.ground_group g on g.oid = c.`group`").rows:
                inst = self.create_instance(self.layers['land'], self.datasets['ground'], str(int(ground)), int(x) + int(offset_x), int(y) + int(offset_y), 0)
                cur_isl.add_tile(inst)
                min_x = int(x) + int(offset_x) if min_x is 0 or int(x) + int(offset_x) < min_x else min_x
                max_x = int(x) + int(offset_x) if max_x is 0 or int(x) + int(offset_x) > max_x else max_x
                max_y = int(y) + int(offset_y) if max_y is 0 or int(y) + int(offset_y) > max_y else max_y
                min_y = int(y) + int(offset_y) if min_y is 0 or int(y) + int(offset_y) < min_y else min_y
            self.island_uid += 1
            self.main.db.query("detach island")

        for x in range(min_x-10, (max_x+11)): # Fill map with water tiles + 10 on each side
            for y in range(min_y-10, max_y+11):
                inst = self.create_instance(self.layers['water'], self.datasets['ground'], str(int(13)), int(x), int(y), 0)

        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "2")[0], fife.ExactModelCoordinate(11, 13, 0), ''))

        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(13, 14, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(12, 14, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(11, 14, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(10, 14, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(10, 13, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(10, 12, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(10, 11, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(10, 10, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(11, 10, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(12, 10, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(13, 10, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(14, 10, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(14, 11, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(14, 12, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(14, 13, 0), ''))
        fife.InstanceVisual.create(self.map.getLayers("id", "layer3")[0].createInstance(self.datasets['building'].getObjects('id', "3")[0], fife.ExactModelCoordinate(14, 14, 0), ''))

        print "center:", ((max_x - min_x) / 2.0), ((max_y - min_y) / 2.0)

        self.cam = self.engine.getView().addCamera("main", self.map.getLayers("id", "layer1")[0], fife.Rect(0, 0, self.main.settings.ScreenWidth, self.main.settings.ScreenHeight), fife.ExactModelCoordinate(((max_x - min_x) / 2.0), ((max_y - min_y) / 2.0), 0.0))
        self.cam.setCellImageDimensions(32, 16)
        self.cam.setRotation(45.0)
        self.cam.setTilt(-60.0)
        self.cam.setZoom(1)

        self.overview = self.engine.getView().addCamera("overview", self.map.getLayers("id", "layer1")[0], fife.Rect(0, self.main.settings.ScreenHeight - 200 if False else 0, 200, 200), fife.ExactModelCoordinate((((max_x - min_x) / 2.0) + 5), ((max_y - min_y) / 2.0), 0.0))
        self.overview.setCellImageDimensions(2, 2)
        self.overview.setRotation(0.0)
        self.overview.setTilt(0.0)
        self.overview.setZoom(100.0 / (1 + max(max_x - min_x, max_y - min_y)))
       

    def creategame(self):
        """Initialises rendering, creates the camera and sets it's position."""

        #create a new player, which is the human player
        self.human_player = Player('Arthus')
        self.players[self.human_player.name] = self.human_player

        self.ingame_gui = IngameGui(self)
        self.ingame_gui.status_set('gold','10000')
        
        #temporary ship creation, should be done automatically in later releases
        self.create_object('99', "content/gfx/dummies/overview/object.png", "content/gfx/sprites/ships/mainship/mainship1.png", "content/gfx/sprites/ships/mainship/mainship3.png", "content/gfx/sprites/ships/mainship/mainship5.png", "content/gfx/sprites/ships/mainship/mainship7.png", self.datasets['building'], 1, 1)
        tempid = self.uid
        inst = self.create_instance(self.layers['land'], self.datasets['building'], '99', 1, 1)
        ship = self.create_unit(self.layers['land'], str(tempid), 99, Ship)
        ship.name = 'Matilde'
        #self.human_player.ships[ship.name] = ship # add ship to the humanplayer


        self.view = self.engine.getView()
        self.view.resetRenderers()


        renderer = self.cam.getRenderer('CoordinateRenderer')
        renderer.clearActiveLayers()
        renderer.addActiveLayer(self.layers['land'])
        
        self.outline_renderer = fife.InstanceRenderer.getInstance(self.cam)

    def create_object(self, oid, image_overview, image_n, image_e, image_s, image_w, dataset, size_x = 1, size_y = 1):
        """Creates a new dataset object, that can later be used on the map
        @var oid: the object oid in the database
        @var image_overview, image_n, image_e, image_s, image_w: str representing the object's images
        @var dataset: the dataset the object is to be created on
        @var size_x: the x-size of the object in grid's
        @var size_y: the y-size of the object in grid's
        """
        obj = dataset.createObject(str(oid), None)
        fife.ObjectVisual.create(obj)
        visual = obj.get2dGfxVisual()
        pool = self.engine.getImagePool()

        img = pool.addResourceFromFile(str(image_overview))
        visual.addStaticImage(0, img)
        visual.addStaticImage(90, img)
        visual.addStaticImage(180, img)
        visual.addStaticImage(270, img)

        img = pool.addResourceFromFile(str(image_n))
        visual.addStaticImage(45, img)
        img = pool.getImage(img)
        img.setXShift(0)#16 - 16 * size_y)
        img.setYShift(-(img.getHeight() - 16) / 2)

        img = pool.addResourceFromFile(str(image_e))
        visual.addStaticImage(135, img)
        img = pool.getImage(img)
        img.setXShift(0)
        img.setYShift(0)

        img = pool.addResourceFromFile(str(image_s))
        visual.addStaticImage(225, img)
        img = pool.getImage(img)
        img.setXShift(0)
        img.setYShift(0)

        img = pool.addResourceFromFile(str(image_w))
        visual.addStaticImage(315, img)
        img = pool.getImage(img)
        img.setXShift(0)
        img.setYShift(0)

        return obj

    def create_instance(self, layer, dataset, id, x, y, z=0):
        """Creates a new instance on the map
        @var layer: layer the instance is created on
        @var id: str with the object id
        @var x, y, z: int coordinates for the new instance
        """
        query = dataset.getObjects('id', str(id))
        if len(query) != 1:
            print(''.join([str(len(query)), ' objects found with id ', str(7), '.']))
        object = query[0]
        inst = layer.createInstance(object, fife.ExactModelCoordinate(x,y,z), str(self.uid))
        self.uid += 1
        fife.InstanceVisual.create(inst)
        return inst

    def create_unit(self, layer, id, object_id, UnitClass):
        """Creates a new unit an the specified layer
        @var layer: fife.Layer the unit is to be created on
        @var id: str containing the object's id
        @var object_id: int containing the objects id in the database
        @var UnitClass: Class of the new unit (e.g. Ship, House)
        @return: returnes a unit of the type specified by UnitClass
        """
        unit = UnitClass(self.model, str(id), layer, self)
        if UnitClass is House:
            res = self.main.db.query("SELECT * FROM data.building WHERE rowid = ?",str(object_id))
            if res.success:
                unit.size_x, unit.size_y = self.main.db.query("SELECT size_x,size_y FROM data.building WHERE rowid = ?",str(object_id)).rows[0]
        self.instance_to_unit[unit.object.getFifeId()] = unit
        unit.start()
        return unit

    def build_check(self, inst):
        """
        Checkes whether or not a building can be built at the current mouse position.
        @var inst: Object instance that is to be built (must have size_x and size_y set).
        @var tile_list: list containing fife.Instances, if specified it is also checked that the instance can
                        only be built on the fife.Instances in the list.
        @return: returns bool true if check successfull and false it. 
        """

        #FIXME: works basically, but will result in problems with unit checking and wrong checks on the lower right side of islands
        def check_inst(layer, point, inst):
            instances = self.cam.getMatchingInstances(self.cam.toScreenCoordinates(point), layer)
            if instances: #Check whether the found instance equals the instance that is to be built.
                if inst.object.getFifeId() == instances[0].getFifeId():
                    instances = instances[1:len(instances)]
            if instances and len(instances) > 0:
                if self._build_tiles is not None:
                    for inst in self._build_tiles:
                        if inst.getLocation() == instances[0].getLocation():
                            return True
                        else:
                            pass
                    return False
                else:
                    return True
            else:
                return False
        checkpoint = inst.object.getLocation().getMapCoordinates()
        starty = float(checkpoint.y)-0.5
        checkpoint.x = float(checkpoint.x)+0.5
        check = True
        print 'Start check x: ', checkpoint.x, ' y: ', starty
        for x in xrange(inst.size_x):
            checkpoint.y = starty
            for y in xrange(inst.size_y):
                print 'Checking x: ', checkpoint.x,' y: ', checkpoint.y
                check = check_inst(self.layers['land'], checkpoint, inst)
                print 'land check:', check
                if check:
                    check = (not check_inst(self.layers['units'], checkpoint, inst))
                    print 'unit check:', check
                else:
                    break
                checkpoint.y += 1
            if not check:
                break
            checkpoint.x += 1
        print 'Finished check'
        return check

    def get_tiles_in_radius(self, layer, radius, start_loc):
        """Returns a list of instances in the radius on the specified layer.
        @var layer: fife.Layer the instances are present on.
        @var radius: int radius that is to be used.
        @var start_loc: fife.Location startpoint.
        @return: list of fife.Instances in the radius arround (startx,starty)."""
        list = []
        generator = (inst for inst in layer.getInstances() if math.fabs(int(inst.getLocation().getMapDistanceTo(start_loc))) <= radius)
        self.outline_renderer.removeAllOutlines()
        for item in generator:
            list.append(item)
            # This is for testing purposes only, should later be done by an own funktion.
            self.outline_renderer.addOutlined(item, 0, 0, 0, 2)
        return list

    def in_radius(self, location_a, location_b, radius):
        """Checks whether location_b is an radius of location_a.
        @var location_a, location_b: fife.Location
        @var radius: int radius
        @return: boolean whether location_b is in radius of location_a
        """
        if int(location_a.getMapDistanceTo(location_b)) <= radius:
            return True
        else:
            return False

    def build_object(self, id, layer, Object, x, y, tile_list):
        """Creates an instance and object for the id and sets the correct mode.
        @var id: str with the objects unique id.
        @var layer: fife.Layer the object is to be built on.
        @var Object: unit.Object class representing the object.
        @var x,y: int coordinates for initial placement.
        @var tile_list: list containing fife.Instances on which the object can be built.
        """
        self.mode = _MODE_BUILD
        self._build_tiles = tile_list
        curunique = self.uid
        inst = self.create_instance(layer , self.datasets['building'], id, x, y)
        self.selected_instance = self.create_unit(layer, curunique, id, Object)


    def get_instance(self, layer, x, y):
        """Returns the first instance found on the layer at gridpoint (x,y).
        @var layer: fife.Layer to look on.
        @var x,y: float grid coordinates
        @return: fife.Instance if an Instance is found, else returns None"""
        instances = layer.getInstances()
        inst = (inst for inst in instances if int(inst.getLocation().getExactLayerCoordinatesRef().x) is x and int(inst.getLocation().getExactLayerCoordinatesRef().y is y)).next()
        if inst: 
            return inst
        else:
            return None

    def create_settlement(self, player, warehouse):
        """Creates a new settlement
        @var player: Player instance that built the settlement
        @var warehouse: the initial warehouse
        """
        pass
        #settlement = Settlement()
        


    def set_cam_position(self, x, y, z):
        """Sets the camera position
        @var pos: tuple with coordinates(x.x,x.x,x.x) to set the camera to.
        """
        loc = fife.Location(self.layers['water'])
        loc.setExactLayerCoordinates(fife.ExactModelCoordinate(x, y, z))
        self.cam.setLocation(loc)

    def move_camera(self, xdir, ydir):
        """Moves the camera across the screen.
        @var xdir: int representing x direction scroll.
        @var ydir: int representing y direction scroll.
        """
        loc = self.cam.getLocationRef()
        cam_scroll = loc.getExactLayerCoordinatesRef()
        if xdir != 0:
            cam_scroll.x += xdir * math.cos(math.pi * self.cam.getRotation() / 180.0) / self.cam.getZoom()
            cam_scroll.y += xdir * math.sin(math.pi * self.cam.getRotation() / 180.0) / self.cam.getZoom()
        if ydir != 0:
            cam_scroll.x += ydir * math.sin(math.pi * self.cam.getRotation() / -180.0) / self.cam.getZoom()
            cam_scroll.y += ydir * math.cos(math.pi * self.cam.getRotation() / -180.0) / self.cam.getZoom()
        self.cam.setLocation(loc)

    def select_unit(self):
        """Runs neccesary steps to select a unit."""
        self.selected_instance.object.say(str(self.selected_instance.health) + '%', 0) # display health over selected ship
        self.outline_renderer.addOutlined(self.selected_instance.object, 255, 255, 255, 1)
        if self.selected_instance.__class__ is Ship:
            self.ingame_gui.gui['ship'].show() #show the gui for ships

    def deselect_unit(self):
        """Runs neccasary steps to deselect a unit."""
        if self.selected_instance.__class__ is Ship:
            self.ingame_gui.toggle_visible('ship') # hide the gui for ships
            self.selected_instance.object.say('') #remove status of last selected unit
            self.outline_renderer.removeAllOutlines() # FIXME: removeOutlined(self.selected_instance.object) doesn't work
           
    def keyPressed(self, evt):
        keyval = evt.getKey().getValue()
        keystr = evt.getKey().getAsString().lower()
        if keyval == fife.Key.LEFT:
            self.move_camera(-1, 0)
        elif keyval == fife.Key.RIGHT:
            self.move_camera(1, 0)
        elif keyval == fife.Key.UP:
            self.move_camera(0, -1)
        elif keyval == fife.Key.DOWN:
            self.move_camera(0, 1)
        elif keystr == 'c':
            r = self.cam.getRenderer('CoordinateRenderer')
            r.setEnabled(not r.isEnabled())
        elif keystr == 'r':
            self.rotate_map_right()
        elif keystr == 'q':
            self.__del__()
            self.main.quit()    
        elif keystr == 't':
            r = self.cam.getRenderer('GridRenderer')
            r.setEnabled(not r.isEnabled())

    def mousePressed(self, evt):
        clickpoint = fife.ScreenPoint(evt.getX(), evt.getY())
        if evt.getX() < 200 and evt.getY() < 200:
            loc = fife.Location(self.layers["water"])
            loc.setExactLayerCoordinates(self.overview.toMapCoordinates(clickpoint, False))
            self.cam.setLocation(loc)
        else:
            if (evt.getButton() == fife.MouseEvent.LEFT):
                if self.mode is _MODE_COMMAND: # standard mode
                    instances = self.cam.getMatchingInstances(clickpoint, self.layers['land'])
                    if instances: #check if clicked point is a unit
                        selected = instances[0]
                        print "selected instance at: ",  selected.getLocation().getMapCoordinates().x, selected.getLocation().getMapCoordinates().y
                        if self.selected_instance:
                            if self.selected_instance.object.getFifeId() != selected.getFifeId():
                                self.deselect_unit()
                        if selected.getFifeId() in self.instance_to_unit:
                            self.selected_instance = self.instance_to_unit[selected.getFifeId()]
                            self.select_unit()
                        else:
                            self.selected_instance = None
                    elif self.selected_instance: # remove unit selection
                        self.deselect_unit()
                        self.selected_instance = None
                else:
                    if self.build_check(self.selected_instance):
                        self.mode = _MODE_COMMAND
                        self.selected_instance = None
                        self._build_tiles = None
            elif (evt.getButton() == fife.MouseEvent.RIGHT):
                if self.mode is _MODE_COMMAND:
                    if self.selected_instance: # move unit   
                        if self.selected_instance.type == 'ship':
                            target_mapcoord = self.cam.toMapCoordinates(clickpoint, False)
                            target_mapcoord.z = 0
                            l = fife.Location(self.layers['land'])
                            l.setMapCoordinates(target_mapcoord)
                            self.selected_instance.move(l)
                else:
                    self.mode = _MODE_COMMAND
                    self.layers['units'].deleteInstance(self.selected_instance.object)
                    self.instance_to_unit[self.selected_instance.object.getFifeId()] = None
                    self.selected_instance = None
                    self._build_tiles = None

    def mouseWheelMovedUp(self, evt):
        self.zoom_in()

    def mouseWheelMovedDown(self, evt):
        self.zoom_out()

    def zoom_out(self):
        zoom = self.cam.getZoom() * 0.875
        if(zoom < 0.25):
            zoom = 0.25
        self.cam.setZoom(zoom)

    def zoom_in(self):
        zoom = self.cam.getZoom() / 0.875
        if(zoom > 1):
            zoom = 1
        self.cam.setZoom(zoom)

    def rotate_map_right(self):
          self.cam.setRotation((self.cam.getRotation() + 90) % 360)

    def rotate_map_left(self):
          self.cam.setRotation((self.cam.getRotation() - 90) % 360)


    def mouseMoved(self, evt):
        if self.mode == _MODE_BUILD:
            pt = fife.ScreenPoint(evt.getX(), evt.getY())
            target_mapcoord = self.cam.toMapCoordinates(pt, False)
            target_mapcoord.x = int(target_mapcoord.x)
            target_mapcoord.y = int(target_mapcoord.y)
            target_mapcoord.z = 0
            l = fife.Location(self.layers['units'])
            l.setMapCoordinates(target_mapcoord)
            self.selected_instance.move(l)
            #print self.build_check(self.selected_instance)
