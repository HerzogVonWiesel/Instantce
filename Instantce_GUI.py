"""
Instantce: Instantly recognize and replace objects with instances!
Authors: Jérôme Stephan & Darby Edelen
"""
PLUGIN_ID = 1061542

import c4d
import os
import sys
import webbrowser 
import math 
import random
import time
from c4d import plugins, gui, bitmaps, documents, storage, utils
from collections import defaultdict
import typing

doc: c4d.documents.BaseDocument  # The currently active document.
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
            for key, data in bc:
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
        uvs = obj.GetTag(c4d.Tuvw).GetLowlevelDataAddressR() if self.consider["uvs"] else None

        #Tags should be the same as well
        tags = frozenset(self._hash_tag(tag, i) for i, tag in enumerate(obj.GetTags()))

        # Hash as many or as few measures as you like together
        instance_ident = hash(hash(point_count) + hash(poly_count) + hash(pts) + hash(uvs) + hash(tags))
        material_tags = [tag for tag in obj.GetTags() if tag.GetType() == c4d.Ttexture]
        self.instance_groups[instance_ident].append((obj, mg, material_tags))

        return instance_ident

    def build_instance_dict(self):
        total_num = self.poly_objs_count
        for i, obj in enumerate(self.poly_objs):
            self._calculate_hash(obj)
            if self.reportBack:
                self.reportBack.UpdateProgressBar(percent=int((i+1)*50/total_num), col=None)


    def create_instances(self):
        if not self.instance_groups:
            self.build_instance_dict()

        count = 0
        total_num = self.poly_objs_count - len(self.instance_groups)

        self.doc.StartUndo()

        for instance_grp in self.instance_groups.values():
            ref_obj, ref_mtx = instance_grp.pop()

            for obj, mtx in instance_grp:
                instance_obj = c4d.InstanceObject()
                if instance_obj is None:
                    raise RuntimeError("Failed to create an instance object.")
                instance_obj.SetReferenceObject(ref_obj)
                instance_obj.SetMl(obj.GetMl() * mtx * ~ref_mtx)
                instance_obj.SetName(obj.GetName())
                instance_obj[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE_SINGLEINSTANCE
                self.doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, instance_obj)
                self.doc.InsertObject(instance_obj, pred = obj)
                self.doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, obj)
                obj.Remove()
                count += 1
                if self.reportBack:
                    self.reportBack.UpdateProgressBar(percent=int((count)*50/total_num)+50, col=None)

        if self.reportBack:
            self.reportBack.StopProgressBar()

        self.doc.EndUndo()

        return count

def startInstantce(objects, instance_args, reportBack):
    start = time.perf_counter()
    blind = instance_args["blind"]

    if blind:
        reportBack = None
    instance_finder = InstanceFinder(objects, 
                                     consider_dict = instance_args["consider"],
                                     precision = instance_args["precision"], 
                                     samples = instance_args["samples"], 
                                     seed = instance_args["seed"],
                                     reportBack = reportBack)
    instance_count = instance_finder.create_instances()
    total_count = instance_finder.poly_objs_count

    duration = time.perf_counter() - start
    if instance_count > 0:
        print(f"Replaced {instance_count} objects with instances in {duration:.03} seconds ({(instance_count/duration):.02f} objects / second). Remaining objects: {total_count - instance_count}")

    c4d.EventAdd()

# Colors
BG_DARK = c4d.Vector(0.1015625, 0.09765625, 0.10546875)
DARK_BLUE_TEXT_COL = c4d.Vector(0, 0.78125, 0.99609375)
DARK_RED_TEXT_COL = c4d.Vector(0.99609375, 0, 0)



# ---------------------------------------------------------------------
#       Creating GUI Instance Functions UI Elements Operations 
#                          Hepler Methods. 
# ---------------------------------------------------------------------

def AddLinkBoxList_GUI(ui_ins, ui_id, w_size, h_size, enable_state_flags):
    """ 
    This GUI name is really call a c4d.gui.InExcludeCustomGui.
    / InExclude custom GUI (CUSTOMGUI_INEXCLUDE_LIST). 
    """
    #First create a container that will hold the items we will allow to be dropped into the INEXCLUDE_LIST gizmo
    acceptedObjs = c4d.BaseContainer()
    acceptedObjs.InsData(c4d.Opolygon, "") # -> # Accept point objects 
                                             # Take a look at c4d Objects Types in SDK.
    # Create another base container for the INEXCLUDE_LIST gizmo's settings and add the above container to it
    bc_IEsettings = c4d.BaseContainer()
    bc_IEsettings.SetData(c4d.IN_EXCLUDE_FLAG_SEND_SELCHANGE_MSG, True)
    bc_IEsettings.SetData(c4d.IN_EXCLUDE_FLAG_INIT_STATE, 1)
    """ 
    Its buttons with states for each object in the list container gui of the CUSTOMGUI_INEXCLUDE_LIST.
    feel free to enable this in the ui by seting the  enable_state_flags to True. 
    """
    if enable_state_flags == True:
        bc_IEsettings.SetData(c4d.IN_EXCLUDE_FLAG_NUM_FLAGS, 1)
        # button 1
        bc_IEsettings.SetData(c4d.IN_EXCLUDE_FLAG_IMAGE_01_ON, c4d.RESOURCEIMAGE_OK) # -> Id Icon or Plugin Id 
        bc_IEsettings.SetData(c4d.IN_EXCLUDE_FLAG_IMAGE_01_OFF, c4d.RESOURCEIMAGE_CANCEL)
        
    bc_IEsettings.SetData(c4d.DESC_ACCEPT, acceptedObjs)        
    # bc_IEsettings.SetData(c4d.DESC_EDITABLE, False)
    ui_ins.AddCustomGui(ui_id, c4d.CUSTOMGUI_INEXCLUDE_LIST, "", c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, w_size, h_size, bc_IEsettings)
    return True


def Add_ProgressBar_GUI(ui_ins, progressbar_ui_id, strText_id, w_size, h_size):
    """
    Create ProgressBar GUI
    """
    ui_ins.GroupBegin(0, c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, 0, 1)   
    ui_ins.GroupBorderNoTitle(c4d.BORDER_THIN_IN)
    # ProgressBar
    ui_ins.AddCustomGui(progressbar_ui_id, c4d.CUSTOMGUI_PROGRESSBAR, "", c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, w_size, h_size)
    ui_ins.AddSeparatorV(0, c4d.BFV_SCALEFIT)
    # Static UI Text
    ui_ins.AddStaticText(strText_id, c4d.BFH_MASK, 50, h_size, "", c4d.BORDER_WITH_TITLE_BOLD) 
    ui_ins.GroupEnd() # Group End           
    return True

def Run_ProcessBar(ui_ins, progressbar_ui_id, percent_ui_id, percent, col):
    # Set Data to PROGRESSBAR
    progressMsg = c4d.BaseContainer(c4d.BFM_SETSTATUSBAR)
    progressMsg[c4d.BFM_STATUSBAR_PROGRESSON] = True
    progressMsg[c4d.BFM_STATUSBAR_PROGRESS] = percent/100.0 
    # this if you want a custom color
    if col:
        ui_ins.SetDefaultColor(progressbar_ui_id, c4d.COLOR_PROGRESSBAR, col)    
    ui_ins.SendMessage(progressbar_ui_id, progressMsg)
    ui_ins.SetString(percent_ui_id, str(int(percent))+"%")
    # Return Percent String Data  
    return int(percent)
  
def Stop_ProgressBar(ui_ins, progressbar_ui_id):
    progressMsg = c4d.BaseContainer(c4d.BFM_SETSTATUSBAR)
    progressMsg.SetBool(c4d.BFM_STATUSBAR_PROGRESSON, False)
    ui_ins.SendMessage(progressbar_ui_id, progressMsg)
    return True

# ------------------------------------------------------------------------------------ #

GROUP_BORDER_SPACE = 6
GROUP_BORDER_SPACE_SM = GROUP_BORDER_SPACE - 2

ID_INEXCLUDE_LIST = 10000
ID_PROCESS_BTN = 10001

ID_PROGRESSBAR = 10100
ID_PROGRESSBAR_TEXT = 10101

ID_PRECISION = 10200
ID_SAMPLES = 10201
ID_SEED = 10202
ID_BLIND_MODE = 10203

ID_CONSIDER_TAGORDER = 10301
ID_CONSIDER_MATERIALS = 10302
ID_CONSIDER_SELECTIONS = 10303
ID_CONSIDER_OTHERTAGS = 10304
ID_CONSIDER_UVS = 10305

ID_BLANK = 101010

# ----------------------------------------
#  // UI Main Window //
# ----------------------------------------
class Tool_WindowDialog(c4d.gui.GeDialog):
    
    # GUI Ids
    IDS_VER = 999
    IDS_OverallGrp = 1000
    IDS_StaticText = 1001 
    IDS_MULTI_LINE_STRINGBOX = 1004

    def Process(self, instance_args):
        LinkList = self.FindCustomGui(ID_INEXCLUDE_LIST, c4d.CUSTOMGUI_INEXCLUDE_LIST)
        ObjectListData = LinkList.GetData()
        objs = [ObjectListData.ObjectFromIndex(doc, i) for i in range(ObjectListData.GetObjectCount()) if ObjectListData.GetFlags(i)]
        if objs:
            startInstantce(objects=objs, instance_args=instance_args, reportBack = self)
        else: 
            print("No Objects in the List")
        return True
    
    def UpdateProgressBar(self, percent, col):
        """ Update Progress Bar """
        # self.SetString(self.IDS_PROCESSBAR_TEXT, Run_ProcessBar(ui_ins=self, progressbar_ui_id=self.IDS_PROCESSBAR_GUI, percent_ui_id=self.IDS_PROCESSBAR_TEXT , percent=percent, col=col))
        Run_ProcessBar(ui_ins=self, progressbar_ui_id=ID_PROGRESSBAR, percent_ui_id=ID_PROGRESSBAR_TEXT , percent=percent, col=col)
        return True
    
    def StopProgressBar(self):
        """ Stop Progress Bar """
        Stop_ProgressBar(ui_ins=self, progressbar_ui_id=ID_PROGRESSBAR)
        return True       
        
    # ====================================== #        
    #  Main GeDialog Class Overrides
    # ====================================== #
    def __init__(self):
        """
        The __init__ is an Constuctor and help get 
        and passes data on from the another class.
        """        
        super(Tool_WindowDialog, self).__init__()

    # UI Layout
    def CreateLayout(self):
        # Dialog Title
        self.SetTitle("Instantce Demo")
        
        # Top Menu addinng Tool Version
        self.GroupBeginInMenuLine()
        self.AddStaticText(self.IDS_VER, 0)
        self.SetString(self.IDS_VER, " v1.0  ")
        self.GroupEnd()        
        
        self.GroupBegin(self.IDS_OverallGrp, c4d.BFH_SCALEFIT, 1, 0, "") # Overall Group.
        
        # Static UI Text
        # self.AddStaticText(self.IDS_StaticText, c4d.BFH_CENTER, 0, 15, "Instantce Demo", c4d.BORDER_WITH_TITLE_BOLD)
        
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT) # Line Separator / eg: self.AddSeparatorH(0, c4d.BFH_MASK) and AddSeparatorV 

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, 2, 0, "") 
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        
        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT, 1, 0, "") 
        self.AddStaticText(ID_BLANK, c4d.BFH_LEFT, 0, 15, " Add Objects :", c4d.BORDER_WITH_TITLE_BOLD)
        AddLinkBoxList_GUI(ui_ins=self, ui_id=ID_INEXCLUDE_LIST, w_size=500, h_size=300, enable_state_flags=True)
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
        self.AddCheckbox(ID_CONSIDER_MATERIALS, c4d.BFH_SCALEFIT, 0, 0, "Material Tags")
        self.AddCheckbox(ID_CONSIDER_SELECTIONS, c4d.BFH_SCALEFIT, 0, 0, "Selection Tags")
        self.AddCheckbox(ID_CONSIDER_OTHERTAGS, c4d.BFH_SCALEFIT, 0, 0, "Other Tags")
        self.AddCheckbox(ID_CONSIDER_TAGORDER, c4d.BFH_SCALEFIT, 0, 0, "Order of Tags")
        self.AddCheckbox(ID_CONSIDER_UVS, c4d.BFH_SCALEFIT, 0, 0, "UVs")
        self.GroupEnd()

        self.GroupBegin(ID_BLANK, c4d.BFH_SCALEFIT)
        self.GroupBorder(c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(GROUP_BORDER_SPACE, GROUP_BORDER_SPACE_SM, GROUP_BORDER_SPACE, GROUP_BORDER_SPACE)
        self.AddCheckbox(ID_BLIND_MODE, c4d.BFH_SCALEFIT, 0, 0, "Blind Mode")
        self.GroupEnd()
        self.GroupEnd()  
        
        self.GroupEnd() 
                      
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        Add_ProgressBar_GUI(ui_ins=self, progressbar_ui_id=ID_PROGRESSBAR, strText_id=ID_PROGRESSBAR_TEXT, w_size=100, h_size=10)
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddButton(ID_PROCESS_BTN, c4d.BFH_SCALEFIT, 0, 30, name="Instantce!") 
        
        # self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
    
        self.GroupEnd() 
        self.GroupEnd() # End of the overall group.        
        return True

    def InitValues(self):
        """ 
        Called when the dialog is initialized by the GUI / GUI's startup values basically.
        """
        # self.SetDefaultColor(self.IDS_OverallGrp, c4d.COLOR_BG, BG_DARK)
        self.SetDefaultColor(self.IDS_StaticText, c4d.COLOR_TEXT, DARK_BLUE_TEXT_COL) 
        self.SetDefaultColor(self.IDS_VER, c4d.COLOR_TEXT, DARK_RED_TEXT_COL)
        self.SetString(ID_PROGRESSBAR_TEXT, "0%")
        self.SetInt32(ID_PRECISION, 3, min=0, max=5, step=1, max2=10)
        self.SetInt32(ID_SAMPLES, 100, min=0, max=1000, step=1, max2=100000)
        self.SetInt32(ID_SEED, 12345, min=0, max=99999, step=1)

        self.SetBool(ID_CONSIDER_TAGORDER, True)
        self.SetBool(ID_CONSIDER_MATERIALS, True)
        self.SetBool(ID_CONSIDER_SELECTIONS, True)
        self.SetBool(ID_CONSIDER_OTHERTAGS, True)
        self.SetBool(ID_CONSIDER_UVS, True)

        selected = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_SELECTIONORDER)
        LinkList =  self.FindCustomGui(ID_INEXCLUDE_LIST, c4d.CUSTOMGUI_INEXCLUDE_LIST)
        LinkListData = LinkList.GetData()
        for obj in selected:
            LinkListData.InsertObject(obj, 1)
        LinkList.SetData(LinkListData)
        
        #self.Enable(self.IDS_MULTI_LINE_STRINGBOX, False)# --> # Disable or Enable Mode of the user interaction       
        return True 
 
    def Command(self, id, msg):
        """
        This Method is called automatically when the user clicks on a gadget and/or changes its value this function will be called.
        It is also called when a string menu item is selected.
        :param messageId: The ID of the gadget that triggered the event.
        :param bc: The original message container
        :return: False if there was an error, otherwise True.
        """
        if (id == ID_PROCESS_BTN):
            consider_dict = {
                "tagorder":     self.GetBool(ID_CONSIDER_TAGORDER),
                "materials":    self.GetBool(ID_CONSIDER_MATERIALS),
                "selections":   self.GetBool(ID_CONSIDER_SELECTIONS),
                "othertags":    self.GetBool(ID_CONSIDER_OTHERTAGS),
                "uvs":          self.GetBool(ID_CONSIDER_UVS),
            }
            instance_args = {
                "precision":    self.GetBool(ID_PRECISION),
                "samples":      self.GetBool(ID_SAMPLES),
                "seed":         self.GetBool(ID_SEED),
                "blind":        self.GetBool(ID_BLIND_MODE),
                "consider":     consider_dict,
            }
            self.Process(instance_args)
                    
        return True
    

    def CoreMessage(self, id, msg):
        """
        Override this function if you want to react to Cinema 4D core messages. 
        The original message is stored in msg
        """     
        if id == c4d.EVMSG_CHANGE:
            pass
        return True



if __name__=='__main__':
    class_dialog = Tool_WindowDialog()
    class_dialog.Open(c4d.DLG_TYPE_ASYNC, defaultw=0, defaulth=0)