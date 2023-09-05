"""
Instantce: Instantly recognize and replace objects with instances!
Authors: Jérôme Stephan & Darby Edelen

Possible future TODO:
    - Speed up tree / list view fns by using deques instead of lists
"""
PLUGIN_ID = 1061542

from typing import Union
import c4d
import os
import sys
import webbrowser
import random
import time
from collections import defaultdict
import typing

from c4d import Vector

doc: c4d.documents.BaseDocument = None # The currently active document.
op: typing.Optional[c4d.BaseObject]  # The selected object within that active document. Can be None.

class InstanceFinder:
    def __init__(self, objects, consider_dict, precision = 3, samples = 100, seed = 12345, reportBack = None, doc = c4d.documents.GetActiveDocument()):
        self.doc = doc
        self.reportBack = reportBack
        self.consider = consider_dict
        self.poly_objs = objects
        self.poly_objs_count = len(objects)
        self.precision = precision
        self.samples = samples
        self.seed = seed
        self.instance_groups = defaultdict(list)

    def get_sample_pts(self, obj, count):
        total_num = obj.GetPointCount()
        count = min(count, total_num)
        
        if count < total_num / 3:
            return self.sample_pts_a(obj, count, total_num)
        else:
            return self.sample_pts_b(obj, count)


    def sample_pts_a(self, obj, count, total_num):
        
        random.seed(123456)
        sample_indices = random.sample(range(total_num), count)
        
        return (obj.GetPoint(i) for i in sample_indices)

    def sample_pts_b(self, obj, count):
        all_points = obj.GetAllPoints()
        
        random.seed(123456)
        samples = random.sample(all_points, count)

        return samples

    def convert_vector(self, vec):
        # The point position comparison appears to be somewhat sensitive
        # to different levels of precision (decimals). I'd like to come up
        # with a more consistent way to prepare floats for equality comparison.

        x = round(vec.x, self.precision)
        y = round(vec.y, self.precision)
        z = round(vec.z, self.precision)
        return (x,y,z)

    def iterate_hierarchy(self, op, type=c4d.BaseObject):
        while op:
            if isinstance(op, type):
                self.poly_obj_count += 1
                yield op
            if op.GetDown():
                op = op.GetDown()
                continue
            while not op.GetNext() and op.GetUp():
                op = op.GetUp()
            op = op.GetNext()

    def _calculate_relative_matrix(self, obj):
        # try catch for when the object has no polygons
        try:
            poly = obj.GetPolygon(0)
        except IndexError:
            print(f"Object {obj.GetName()} has no polygons, aborting.")
            return None

        off = obj.GetPoint(poly.a)
        v2 = obj.GetPoint(poly.b) - off
        scale = v2.GetLength()
        v2.Normalize()
        v3 = (v2 % (obj.GetPoint(poly.c) - off)).GetNormalized()
        v1 = v2 % v3
        v1 *= scale
        v2 *= scale
        v3 *= scale
        return c4d.Matrix(off, v1, v2, v3);

    def _hash_base_container(self, bc):
        def traverse_bc(bc):
            ignore_keys = [1011, 1012, 1013] if bc[1004] == 6 else [] # Ignore texture positions if tag is set to UVW
            for key, data in bc:
                if key in ignore_keys:
                    continue
                if type(data) == c4d.BaseContainer:
                    yield from traverse_bc(data)
                else:
                    yield data

        return hash(tuple(traverse_bc(bc)))

    def _hash_tag(self, tag, index = 0):
        if self.consider['materials'] and tag.GetType() == c4d.Ttexture:
            mat = tag.GetMaterial()

            if mat:
                bc = tag.GetData()
                # print(self._hash_base_container(bc))
                poly_select = bc.GetString(c4d.TEXTURETAG_RESTRICTION)

                if poly_select:
                    poly_select_tags = [s for s in tag.GetObject().GetTags() if s.GetName() == poly_select]

                    if poly_select_tags:
                        poly_select_tag = poly_select_tags[0]
                        obj = poly_select_tag.GetObject()

                        return hash(
                            index +
                            hash(mat) +
                            hash(tuple(poly_select_tag.GetBaseSelect().GetAll(obj.GetPolygonCount()))) +
                            self._hash_base_container(bc)
                        )
                return hash(index + hash(mat) + self._hash_base_container(bc))

        if self.consider['normals'] and tag.GetType() in (c4d.Tphong, c4d.Tnormal):
            if not tag.GetObject().GetTag(c4d.Tnormal):
                # Hash Phong tag because there are no Normal tags
                return self._hash_base_container(tag.GetData())

            # Hash Normal tag
            return hash(tag.GetLowlevelDataAddressR())

        if self.consider['uvs'] and tag.GetType() == c4d.Tuvw:
            return hash(tag.GetLowlevelDataAddressR())


    def _calculate_hash(self, obj):
        """
            This function returns a unique hash for unique c4d.PolygonObjects
        """

        # Point Count is one measure of uniqueness
        point_count = obj.GetPointCount()

        # Poly Count is another measure of uniqueness
        poly_count = obj.GetPolygonCount()

        # Calculating the local point positions is challenging, but a good indicator of uniqueness
        mg = self._calculate_relative_matrix(obj)
        if not mg:
            return None
        pts = frozenset(self.convert_vector(pt * ~mg) for pt in self.get_sample_pts(obj, self.samples))

        # UVs are another measure of uniqueness
        # uvs = obj.GetTag(c4d.Tuvw).GetLowlevelDataAddressR() if self.consider["uvs"] else None

        #Tags should be the same as well
        tags = frozenset(self._hash_tag(tag, i) for i, tag in enumerate(obj.GetTags()))

        # Hash as many or as few measures as you like together
        instance_ident = hash(hash(point_count) + hash(poly_count) + hash(pts) + hash(tags))
        material_tags = [tag for tag in obj.GetTags() if tag.GetType() == c4d.Ttexture]
        self.instance_groups[instance_ident].append({"obj": obj, "mg": mg, "mat_tags": material_tags, "hash": instance_ident, "opened": True})

        return instance_ident

    def build_instance_dict(self):
        total_num = self.poly_objs_count
        for i, obj in enumerate(self.poly_objs):
            self._calculate_hash(obj)
            if self.reportBack:
                self.reportBack.UpdateProgressBar(percent=int((i+1)*100/total_num), col=None)
        if self.reportBack:
            self.reportBack.StopProgressBar()


    def create_instances(self):
        if not self.instance_groups:
            self.build_instance_dict()

        count = 0
        total_num = self.poly_objs_count - len(self.instance_groups)

        self.doc.StartUndo()

        for instance_grp in self.instance_groups.values():
            instance_grp.reverse()
            element = instance_grp.pop()
            ref_obj = element["obj"]
            ref_mtx = element["mg"]
            ref_materials = element["mat_tags"]

            if not self.consider["materials"]:
                ref_parent = c4d.BaseObject(c4d.Onull)
                self.doc.InsertObject(ref_parent, pred = ref_obj)
                self.doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, ref_parent)
                ref_parent.SetMg(ref_obj.GetMg())
                ref_parent.SetName(f"{ref_obj.GetName()}_parent")
                self.doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, ref_obj)
                ref_obj.Remove()
                self.doc.InsertObject(ref_obj, parent = ref_parent)
                self.doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, ref_obj)
                ref_obj.SetMl(c4d.Matrix())

                for material in ref_materials:
                    self.doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, material)
                    material.Remove()
                    ref_parent.InsertTag(material)

            for element in instance_grp:
                obj = element["obj"]
                mtx = element["mg"]
                materials = element["mat_tags"]

                instance_obj = c4d.InstanceObject()
                if instance_obj is None:
                    raise RuntimeError("Failed to create an instance object.")
                instance_obj.SetReferenceObject(ref_obj)
                instance_obj.SetMl(obj.GetMl() * mtx * ~ref_mtx)
                instance_obj.SetName(obj.GetName())
                instance_obj[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE_SINGLEINSTANCE

                if not self.consider["materials"]:
                    for material in materials:
                        self.doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, material)
                        material.Remove()
                        instance_obj.InsertTag(material)

                self.doc.InsertObject(instance_obj, pred = obj)
                self.doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, instance_obj)
                self.doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, obj)
                obj.Remove()
                count += 1
                if self.reportBack:
                    self.reportBack.UpdateProgressBar(percent=int((count)*100/total_num), col=None)

        if self.reportBack:
            self.reportBack.StopProgressBar()

        self.doc.EndUndo()

        return True

# Colors
BG_DARK = c4d.Vector(0.13, 0.13, 0.13)
BG_DARKER = c4d.Vector(0.11, 0.11, 0.11)
DARK_BLUE_TEXT_COL = c4d.Vector(0, 0.78125, 0.99609375)
ACCENT_COL = c4d.Vector(1, 0.337, 0)
ACCENT_COL_C4D = c4d.Vector(.36, 0.38, .65)

# ---------------------------------------------------------------------
#       Creating GUI Instance Functions UI Elements Operations 
#                          Hepler Methods. 
# ---------------------------------------------------------------------

#----------------------------------------------------------------------
#  TreeViewFunctions Class
#----------------------------------------------------------------------

class InstanceListFns(c4d.gui.TreeViewFunctions):
    def GetBackgroundColor(self, root: object, userdata: object, obj: object, line: int, col: int | Vector) -> int | Vector:
        return BG_DARKER if line % 2 else BG_DARK
    def EmptyText(self, root: object, userdata: object) -> str:
        return "Add objects by dragging them here, \nor opening Instantce! with objects selected."
    def GetFirst(self, root, userdata):
        return root[0] if root else None
        return root.GetFirstObject()
    def GetDown(self, root, userdata, obj):
        return None
        return obj.GetDown()
    def GetNext(self, root, userdata, obj):
        currentObjIndex = root.index(obj)
        return root[currentObjIndex+1] if currentObjIndex+1 < len(root) else None
    def GetPred(self, root, userData, item):
        """
        Gets the predecessor item for #item in #data.
        """
        i: int = root.index(item)
        return root[i-1] if (i - 1) >= 0 else None
    def IsOpened(self, root, userdata, obj):
        return obj.GetBit(c4d.BIT_OFOLD)
    def Open(self, root, userdata, obj, onoff):
        if onoff:
            obj.SetBit(c4d.BIT_OFOLD)
        else:
            obj.DelBit(c4d.BIT_OFOLD)
    def IsSelected(self, root, userdata, obj):
        return obj.GetBit(c4d.BIT_ACTIVE)
    def Select(self, root, userdata, obj, mode):
        if mode == c4d.SELECTION_NEW:
            obj.SetBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj, c4d.SELECTION_NEW)
        elif mode == c4d.SELECTION_ADD:
            obj.SetBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj, c4d.SELECTION_ADD)
        else:
            obj.DelBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj, c4d.SELECTION_SUB)
        c4d.EventAdd()
    def GetID(self, root, userdata, obj):
        return obj.GetGUID()
    def GetName(self, root, userdata, obj):
        return obj.GetName()
    def GetDragType(self, root, userdata, obj):
        return c4d.DRAGTYPE_ATOMARRAY
    def AcceptDragObject(self, root, userdata, obj, dragtype, dragobject):
        if dragtype == c4d.DRAGTYPE_ATOMARRAY:
            return c4d.INSERT_UNDER, False
        return 0
    def InsertObject(self, root, userData, item, dragType: int, dragData: any, insertMode: int, doCopy: bool) -> None:
        """
        Called by Cinema 4D once a drag event has finished which before has been indicated as valid by #AcceptDragObject.
        """
        new_items = [item for item in dragData if item not in root and item.GetType() == c4d.Opolygon]
        root.extend(new_items)
    def DeletePressed(self, root: object, userdata: object) -> None:
        for element in reversed(root):
            if self.IsSelected(root, userdata, element):
                root.remove(element)

class InstanceTreeFns(c4d.gui.TreeViewFunctions):
    def GetBackgroundColor(self, root: object, userdata: object, obj: object, line: int, col: int | Vector) -> int | Vector:
        return BG_DARKER if line % 2 else BG_DARK
    def GetFirst(self, root, userdata):
        return root[list(root.keys())[0]][0]
        return root[0] if root else None
    def GetDown(self, root, userdata, obj):
        if root[obj["hash"]].index(obj) == 0:
            return root[obj["hash"]][1] if len(root[obj["hash"]]) > 1 else None
        return None
    def GetNext(self, root, userdata, obj):
        if root[obj["hash"]].index(obj) == 0:
            key_list = list(root.keys())
            return root[key_list[key_list.index(obj["hash"])+1]][0] if key_list.index(obj["hash"])+1 < len(key_list) else None
        else:
            currentObjIndex = root[obj["hash"]].index(obj)
            return root[obj["hash"]][currentObjIndex+1] if currentObjIndex+1 < len(root[obj["hash"]]) else None
    def IsOpened(self, root, userdata, obj):
        return obj["opened"]
    def Open(self, root, userdata, obj, onoff):
        if onoff:
            obj["opened"] = True
        else:
            obj["opened"] = False
    def IsSelected(self, root, userdata, obj):
        return obj["obj"].GetBit(c4d.BIT_ACTIVE)
    def Select(self, root, userdata, obj, mode):
        if mode == c4d.SELECTION_NEW:
            obj["obj"].SetBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj["obj"], c4d.SELECTION_NEW)
        elif mode == c4d.SELECTION_ADD:
            obj["obj"].SetBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj["obj"], c4d.SELECTION_ADD)
        else:
            obj["obj"].DelBit(c4d.BIT_ACTIVE)
            doc.SetActiveObject(obj["obj"], c4d.SELECTION_SUB)
        c4d.EventAdd()
    def GetID(self, root, userdata, obj):
        return obj["obj"].GetGUID()
    def GetName(self, root, userdata, obj):
        return obj["obj"].GetName()

####################################################################################################
##                                                                                                ##
##                                             UI                                                 ##
##                                                                                                ##
####################################################################################################

VERSION_NUMBER = " v1.0 "
ABOUT_TEXT_COPYRIGHT = "©2023 by Jérôme Stephan & Darby Edelen"
ABOUT_TEXT_WEBSITE = "https://jeromestephan.de"
ABOUT_LINK_README = "https://jeromestephan.gumroad.com/l/Instantce?layout=profile"
ABOUT_SUPPORT = "https://jeromestephan.gumroad.com/"

GROUP_BORDER_SPACE = 6
GROUP_BORDER_SPACE_SM = GROUP_BORDER_SPACE - 2

ID_LINK_ABOUT = 11000
ID_LINK_README = 11001
ID_AUTHOR_TEXT = 11002
ID_LINK_WEBSITE = 11003
ID_SUPPORT_ME = 11004
ID_VERSION_NUMBER = 11005

ID_INEXCLUDE_LIST = 10000
ID_EXTRACT_BTN = 10001
ID_PROCESS_BTN = 10002

ID_PROGRESSBAR = 10100
ID_PROGRESSBAR_TEXT = 10101

ID_PRECISION = 10200
ID_SAMPLES = 10201
ID_SEED = 10202
ID_BLIND_MODE = 10203

ID_CONSIDER_TAGORDER = 10301
ID_CONSIDER_MATERIALS = 10302
ID_CONSIDER_NORMALS = 10303
ID_CONSIDER_OTHERTAGS = 10304
ID_CONSIDER_UVS = 10305

ID_BLANK = 101010

class MainDialog(c4d.gui.GeDialog):

    def AddTreeView(self, w_size, h_size):
        bc_IEsettings = c4d.BaseContainer()
        bc_IEsettings.SetData(c4d.TREEVIEW_OUTSIDE_DROP, True)
        bc_IEsettings.SetData(c4d.TREEVIEW_ALTERNATE_BG, True)
        self._treeView = self.AddCustomGui(ID_INEXCLUDE_LIST, c4d.CUSTOMGUI_TREEVIEW, "", c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, w_size, h_size, bc_IEsettings)
        tree_settings = c4d.BaseContainer()
        tree_settings.SetInt32(0, c4d.LV_TREE)
        self._treeView.SetLayout(1, tree_settings)
        return True
    
    def UpdateTreeView(self, root, treeViewFns):
        self._treeView.SetRoot(root, treeViewFns, None)
        self._treeView.Refresh()
        return True
    
    def Extract(self, instance_args):
        if self._listViewRoot:
            start = time.perf_counter()
            blind = instance_args["blind"]
            reportBack = None if blind else self
            self._instanceFinder = InstanceFinder(self._listViewRoot, 
                                            consider_dict = instance_args["consider"],
                                            precision = instance_args["precision"], 
                                            samples = instance_args["samples"], 
                                            seed = instance_args["seed"],
                                            reportBack = reportBack,
                                            doc = doc)
            self._instanceFinder.build_instance_dict()
            instance_count = len(self._instanceFinder.instance_groups)
            total_count = self._instanceFinder.poly_objs_count

            duration = time.perf_counter() - start
            if instance_count > 0:
                print(f"Recognized {total_count - instance_count} objects with instances in {duration:.03} seconds ({((total_count - instance_count)/duration):.02f} objects / second). Remaining objects: {instance_count}")
                self.UpdateTreeView(self._instanceFinder.instance_groups, InstanceTreeFns())
            c4d.EventAdd()
        else: 
            print("No Objects in the List")
        return True
    
    def ClearExtraction(self):
        self._instanceFinder = None
        self.UpdateTreeView(self._listViewRoot, self._listViewFns)
        return True

    def Process(self):
        if self._instanceFinder:
            start = time.perf_counter()
            self._instanceFinder.create_instances()
            instance_count = len(self._instanceFinder.instance_groups)
            total_count = self._instanceFinder.poly_objs_count

            duration = time.perf_counter() - start
            if instance_count > 0:
                print(f"Replaced {total_count - instance_count} objects with instances in {duration:.03} seconds ({((total_count - instance_count)/duration):.02f} objects / second). Remaining objects: {instance_count}")
                self._listViewRoot = []
                self.UpdateTreeView(self._listViewRoot, self._listViewFns)
            c4d.EventAdd()
        else:
            print("No Instances extracted yet")
            return False
        return True
    
    def AddProgressBar(self, w_size, h_size):
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 0, 1)   
        self.GroupBorderNoTitle(c4d.BORDER_THIN_IN)
        self.AddCustomGui(ID_PROGRESSBAR, c4d.CUSTOMGUI_PROGRESSBAR, "", c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, w_size, h_size)
        self.AddSeparatorV(0, c4d.BFV_SCALEFIT)
        self.AddStaticText(ID_PROGRESSBAR_TEXT, c4d.BFH_MASK, 50, h_size, "", c4d.BORDER_WITH_TITLE_BOLD) 
        self.GroupEnd()
        return True
    
    def UpdateProgressBar(self, percent, col):
        progressMsg = c4d.BaseContainer(c4d.BFM_SETSTATUSBAR)
        progressMsg[c4d.BFM_STATUSBAR_PROGRESSON] = True
        progressMsg[c4d.BFM_STATUSBAR_PROGRESS] = percent/100.0 
        # this if you want a custom color
        if col:
            self.SetDefaultColor(ID_PROGRESSBAR, c4d.COLOR_PROGRESSBAR, col)    
        self.SendMessage(ID_PROGRESSBAR, progressMsg)
        self.SetString(ID_PROGRESSBAR_TEXT, str(int(percent))+"%")
        return True
    
    def StopProgressBar(self):
        progressMsg = c4d.BaseContainer(c4d.BFM_SETSTATUSBAR)
        progressMsg.SetBool(c4d.BFM_STATUSBAR_PROGRESSON, False)
        self.SendMessage(ID_PROGRESSBAR, progressMsg)
        return True
        
    # ====================================== #        
    #  Main GeDialog Class Overrides
    # ====================================== #
    def __init__(self):
        """
        The __init__ is an Constuctor and help get 
        and passes data on from the another class.
        """      
        self._instanceFinder: InstanceFinder | None = None  
        self._treeView: c4d.gui.TreeViewCustomGui | None = None
        self._listViewFns = InstanceListFns()
        self._treeViewFns = InstanceTreeFns()
        self._listViewRoot = None
        self._treeViewRoot = None
        self.extracted = False
        # super(Tool_WindowDialog, self).__init__()

    # UI Layout
    def CreateLayout(self):
        # Dialog Title
        self.SetTitle("Instantce!")
        
        self.MenuSubBegin("About")
        self.MenuAddString(ID_LINK_ABOUT, "About")
        self.MenuAddString(ID_LINK_README, "Readme")
        self.MenuSubEnd()
        
        self.MenuSubBegin("Support this project & me!")
        self.MenuAddString(ID_SUPPORT_ME, "Support this & other projects (& me) on Gumroad!")
        self.MenuSubEnd()
        self.MenuFinished()
        
        # Top Menu addinng Tool Version
        self.GroupBeginInMenuLine()
        self.AddStaticText(ID_VERSION_NUMBER, 0)
        self.SetString(ID_VERSION_NUMBER, VERSION_NUMBER)
        self.GroupEnd()        
        
        # self.GroupBegin(self.IDS_OverallGrp, c4d.BFH_SCALEFIT, 1, 0, "") # Overall Group.
        
        # Static UI Text
        # self.AddStaticText(self.IDS_StaticText, c4d.BFH_CENTER, 0, 15, "Instantce Demo", c4d.BORDER_WITH_TITLE_BOLD)
        
        # self.AddSeparatorH(0, c4d.BFH_SCALEFIT) # Line Separator / eg: self.AddSeparatorH(0, c4d.BFH_MASK) and AddSeparatorV 

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 2, 0, "") 
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0, "") 
        self.AddStaticText(ID_BLANK, c4d.BFH_LEFT, 0, 15, " Objects :", c4d.BORDER_WITH_TITLE_BOLD)
        self.AddTreeView(w_size=500, h_size=300)
        self.GroupEnd()        

        # self.AddSeparatorV(0, c4d.BFV_SCALEFIT)
        
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT|c4d.BFV_TOP, 1, 0, "")
        self.AddStaticText(ID_BLANK, c4d.BFH_LEFT, 0, 15, " Settings :", c4d.BORDER_WITH_TITLE_BOLD)
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Precision")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddEditSlider(ID_PRECISION, c4d.BFH_SCALEFIT, 0, 0)
        self.GroupEnd()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Samples")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddEditSlider(ID_SAMPLES, c4d.BFH_SCALEFIT, 0, 0)
        self.GroupEnd()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Sampling Seed")
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddEditSlider(ID_SEED, c4d.BFH_SCALEFIT, 0, 0)
        self.GroupEnd()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="Consider", cols=1)
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddCheckbox(ID_CONSIDER_MATERIALS, c4d.BFH_SCALEFIT, 0, 0, "Materials")
        self.AddCheckbox(ID_CONSIDER_NORMALS, c4d.BFH_SCALEFIT, 0, 0, "Normals")
        self.AddCheckbox(ID_CONSIDER_UVS, c4d.BFH_SCALEFIT, 0, 0, "UVs")
        self.GroupEnd()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT)
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddCheckbox(ID_BLIND_MODE, c4d.BFH_SCALEFIT, 0, 0, "Blind Mode")
        self.GroupEnd()

        self.GroupEnd() 
        self.GroupEnd() # After this, we are in Overall group.
                      
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddProgressBar(w_size=100, h_size=10)
        # self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="", cols = 2)
        self.AddButton(ID_EXTRACT_BTN, c4d.BFH_SCALEFIT, 0, 30, name="Extract Instances") 
        self.AddButton(ID_PROCESS_BTN, c4d.BFH_SCALEFIT, 0, 30, name="Instantce!") 
        self.GroupEnd()

        # self.AddSubDialog(ID_BLANK, c4d.BFV_SCALEFIT, 0, 0)
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, title="About", cols = 2)
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddSubDialog(ID_BLANK, c4d.BFH_SCALEFIT, 0, 0)
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_RIGHT, 0, 0, ABOUT_TEXT_COPYRIGHT)
        # self.AddRadioText(ID_LINK_WEBSITE, c4d.BFH_FIT, 0, 0, ABOUT_TEXT_WEBSITE)
        self.GroupEnd()
        
        # self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        # self.GroupEnd() # End of the overall group.        
        return True

    def InitValues(self):
        """ 
        Called when the dialog is initialized by the GUI / GUI's startup values basically.
        """
        global doc
        doc =  c4d.documents.GetActiveDocument()
        self.SetDefaultColor(ID_INEXCLUDE_LIST, c4d.COLOR_BG, BG_DARKER)
        self.SetDefaultColor(ID_VERSION_NUMBER, c4d.COLOR_TEXT, ACCENT_COL_C4D)
        self.SetString(ID_PROGRESSBAR_TEXT, "0%")
        self.SetInt32(ID_PRECISION, 3, min=0, max=5, step=1, max2=10)
        self.SetInt32(ID_SAMPLES, 100, min=0, max=1000, step=1, max2=100000)
        self.SetInt32(ID_SEED, 12345, min=0, max=99999, step=1)

        # self.SetBool(ID_CONSIDER_TAGORDER, True)
        self.SetBool(ID_CONSIDER_NORMALS, True)
        self.SetBool(ID_CONSIDER_UVS, True)

        self.Enable(ID_PROCESS_BTN, False)

        self._listViewRoot = [obj for obj in doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN) if obj.GetType() == c4d.Opolygon] #c4d.GETACTIVEOBJECTFLAGS_SELECTIONORDER)]
        self.UpdateTreeView(self._listViewRoot, self._listViewFns)
        return True 
 
    def Command(self, id, msg):
        """
        This Method is called automatically when the user clicks on a gadget and/or changes its value this function will be called.
        It is also called when a string menu item is selected.
        :param messageId: The ID of the gadget that triggered the event.
        :param bc: The original message container
        :return: False if there was an error, otherwise True.
        """
        if (id == ID_EXTRACT_BTN and not self.extracted):
            consider_dict = {
                "materials":    self.GetBool(ID_CONSIDER_MATERIALS),
                "normals":   self.GetBool(ID_CONSIDER_NORMALS),
                "uvs":          self.GetBool(ID_CONSIDER_UVS),
            }
            instance_args = {
                "precision":    self.GetBool(ID_PRECISION),
                "samples":      self.GetBool(ID_SAMPLES),
                "seed":         self.GetBool(ID_SEED),
                "blind":        self.GetBool(ID_BLIND_MODE),
                "consider":     consider_dict,
            }
            self.Extract(instance_args)
            self.extracted = True
            self.SetString(ID_EXTRACT_BTN, "Clear Instances")
            self.Enable(ID_PROCESS_BTN, True)
        
        elif (id == ID_EXTRACT_BTN and self.extracted):
            self.ClearExtraction()
            self.extracted = False
            self.SetString(ID_EXTRACT_BTN, "Extract Instances")
            self.Enable(ID_PROCESS_BTN, False)

        elif (id == ID_PROCESS_BTN):
            self.extracted = False
            self.SetString(ID_EXTRACT_BTN, "Extract Instances")
            self.Enable(ID_PROCESS_BTN, False)
            self.Process()



        
        elif id == ID_LINK_ABOUT:
            about_dlg = AboutDialog()
            about_dlg.Open(c4d.DLG_TYPE_MODAL, xpos=-2, ypos=-2)
        elif id == ID_LINK_README:
            webbrowser.open(ABOUT_LINK_README)
        elif id == ID_LINK_WEBSITE:
            webbrowser.open(ABOUT_TEXT_WEBSITE)
        elif id == ID_SUPPORT_ME:
            webbrowser.open(ABOUT_SUPPORT)
                    
        return True
    

    def CoreMessage(self, id, msg):
        """
        Override this function if you want to react to Cinema 4D core messages. 
        The original message is stored in msg
        """     
        if id == c4d.EVMSG_CHANGE:
            pass
        return True

class AboutDialog(c4d.gui.GeDialog):
    def CreateLayout(self):
        self.SetTitle("About")
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, "Instantce")
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, VERSION_NUMBER)
        self.AddStaticText(ID_BLANK, c4d.BFH_CENTER, 0, 0, "Instantly recognize & replace identical objects with instances!")
        self.AddSeparatorH(c4d.BFH_SCALEFIT)
        self.AddStaticText(ID_AUTHOR_TEXT, c4d.BFH_FIT, 0, 0, "Authors:\t\tMarvin Jérôme Stephan & Darby Edelen")
        self.AddRadioText(ID_SUPPORT_ME, c4d.BFH_FIT, 0, 0, "Support me:\t" + ABOUT_SUPPORT)
        self.AddRadioText(ID_LINK_WEBSITE, c4d.BFH_FIT, 0, 0, "Website:\t\t" + ABOUT_TEXT_WEBSITE)
        return True
    
    def Command(self, mid, msg):
        if mid == ID_SUPPORT_ME:
            webbrowser.open(ABOUT_SUPPORT)
        elif mid == ID_LINK_WEBSITE:
            webbrowser.open(ABOUT_TEXT_WEBSITE)
        return True


class MainDialogCommand(c4d.plugins.CommandData):
    dlg = None
    def Execute(self, doc):
        if self.dlg is None:
            self.dlg = MainDialog()
        return self.dlg.Open(c4d.DLG_TYPE_ASYNC, pluginid=PLUGIN_ID, defaultw=0, defaulth=0, xpos=-2, ypos=-2)
    
    def RestoreLayout(self, sec_ref):
        if self.dlg is None:
            self.dlg = MainDialog()
        return self.dlg.Restore(pluginid=PLUGIN_ID, secret=sec_ref)

if __name__=='__main__':
    directory, _ = os.path.split(__file__)
    icon = os.path.join(directory, "res", "Instantce.tif")
    bmp = c4d.bitmaps.BaseBitmap()
    if bmp.InitWith(icon)[0] != c4d.IMAGERESULT_OK:
        raise MemoryError("Failed to initialize the BaseBitmap.")
    c4d.plugins.RegisterCommandPlugin(id=PLUGIN_ID, 
                                      str="Instantce!", 
                                      info=0, 
                                      help="Instantly recognize & replace identical objects with instances!", 
                                      dat=MainDialogCommand(), 
                                      icon=bmp)