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
import symbol_parser

class InstanceFinder:
    def __init__(self, objects, consider_dict, precision = 3, samples = 100, seed = 12345, reportBack = None, doc = documents.GetActiveDocument()):
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

    def _hash_tag(self, tag, index = 0, mtx = c4d.Matrix()):
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
            if tag.GetType() == c4d.Tnormal:
                normal_data = tag.GetLowlevelDataAddressR()
                normal_data = normal_data.cast('h', [len(normal_data)//6, 3])
                normals = tuple(self.convert_vector(c4d.Vector(x / 32000., y / 32000., z / 32000.) * ~mtx) for x, y, z in normal_data.tolist())
                return hash(normals)

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
        tags = frozenset(self._hash_tag(tag, i, mg) for i, tag in enumerate(obj.GetTags()))

        # Hash as many or as few measures as you like together
        instance_ident = hash(hash(point_count) + hash(poly_count) + hash(pts) + hash(tags))
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
            ref_obj, ref_mtx, ref_materials = instance_grp.pop()

            if len(instance_grp) > 0:
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

                for obj, mtx, materials in instance_grp:
                    instance_obj = c4d.InstanceObject()
                    
                    if instance_obj is None:
                        raise RuntimeError("Failed to create an instance object.")
                    
                    instance_obj.SetReferenceObject(ref_obj)
                    instance_obj.SetMl(obj.GetMl() * mtx * ~ref_mtx)
                    instance_obj.SetName(obj.GetName())
                    instance_obj[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE_SINGLEINSTANCE

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
                                     reportBack = reportBack,
                                     doc = documents.GetActiveDocument())
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

# ----------------------------------------
#  // UI Object List Subdialog //
# ----------------------------------------

class InstanceObjectListDialog(c4d.gui.SubDialog):
    def __init__(self):  
        super().__init__()

    def CreateLayout(self):
        #First create a container that will hold the items we will allow to be dropped into the INEXCLUDE_LIST gizmo
        acceptedObjs = c4d.BaseContainer()
        acceptedObjs.InsData(c4d.Opolygon, "") # -> # Accept point objects 
                                                # Take a look at c4d Objects Types in SDK.
        # Create another base container for the INEXCLUDE_LIST gizmo's settings and add the above container to it
        bc = c4d.BaseContainer()
        bc.SetData(c4d.IN_EXCLUDE_FLAG_SEND_SELCHANGE_MSG, True)
        bc.SetData(c4d.IN_EXCLUDE_FLAG_INIT_STATE, 1)
        """ 
        Its buttons with states for each object in the list container gui of the CUSTOMGUI_INEXCLUDE_LIST.
        feel free to enable this in the ui by seting the  enable_state_flags to True. 
        """
        bc.SetData(c4d.IN_EXCLUDE_FLAG_NUM_FLAGS, 1)
        # button 1
        bc.SetData(c4d.IN_EXCLUDE_FLAG_IMAGE_01_ON, c4d.RESOURCEIMAGE_OK) # -> Id Icon or Plugin Id 
        bc.SetData(c4d.IN_EXCLUDE_FLAG_IMAGE_01_OFF, c4d.RESOURCEIMAGE_CANCEL)

        bc.SetData(c4d.DESC_ACCEPT, acceptedObjs)        

        self.AddCustomGui(INSTANTCE_ID_INEXCLUDE_LIST, c4d.CUSTOMGUI_INEXCLUDE_LIST, "", c4d.BFH_SCALEFIT|c4d.BFV_SCALEFIT, 0, 0, bc)
        return True


# ----------------------------------------
#  // UI Main Window //
# ----------------------------------------
class InstantceMainDialog(c4d.gui.GeDialog):
    # ====================================== #        
    #  Main GeDialog Class Overrides
    # ====================================== #
    def __init__(self):
        """
        The __init__ is an Constuctor and help get 
        and passes data on from the another class.
        """        
        super(InstantceMainDialog, self).__init__()

        self.object_list_subdlg = InstanceObjectListDialog()


    def Process(self, instance_args):
        doc = documents.GetActiveDocument()
        LinkList = self.object_list_subdlg.FindCustomGui(INSTANTCE_ID_INEXCLUDE_LIST, c4d.CUSTOMGUI_INEXCLUDE_LIST)
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
        Run_ProcessBar(ui_ins=self, progressbar_ui_id=INSTANTCE_ID_PROGRESSBAR, percent_ui_id=INSTANTCE_ID_PROGRESSBAR_TEXT , percent=percent, col=col)
        return True


    def StopProgressBar(self):
        """ Stop Progress Bar """
        Stop_ProgressBar(ui_ins=self, progressbar_ui_id=INSTANTCE_ID_PROGRESSBAR)
        return True       
        

    # UI Layout
    def CreateLayout(self):
        result =  self.LoadDialogResource(DLG_INSTANTCE_MAIN)

        if not self.AttachSubDialog(self.object_list_subdlg, DLG_INSTANTCE_OBJECT_LIST):
            raise RuntimeError("Failed to attach subdialog element.")

        self.LayoutChanged(DLG_INSTANTCE_OBJECT_LIST)

        return result


    def InitValues(self):
        """ 
        Called when the dialog is initialized by the GUI / GUI's startup values basically.
        """
        # self.SetDefaultColor(self.IDS_OverallGrp, c4d.COLOR_BG, BG_DARK)
        # self.SetDefaultColor(self.IDS_StaticText, c4d.COLOR_TEXT, DARK_BLUE_TEXT_COL) 
        self.SetDefaultColor(INSTANTCE_ID_VER, c4d.COLOR_TEXT, DARK_RED_TEXT_COL)
        self.SetString(INSTANTCE_ID_PROGRESSBAR_TEXT, "0%")
        self.SetInt32(INSTANTCE_ID_PRECISION, 3, min=1, max=5, step=1, min2=1, max2=10)
        self.SetInt32(INSTANTCE_ID_SAMPLES, 100, min=10, max=1000, step=1, min2=10, max2=100000)
        self.SetInt32(INSTANTCE_ID_SEED, 12345, min=0, max=99999, step=1)

        self.SetBool(INSTANTCE_ID_CONSIDER_MATERIALS, False)
        self.SetBool(INSTANTCE_ID_CONSIDER_NORMALS, True)
        self.SetBool(INSTANTCE_ID_CONSIDER_UVS, True)

        selected = documents.GetActiveDocument().GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_SELECTIONORDER)
        LinkList =  self.object_list_subdlg.FindCustomGui(INSTANTCE_ID_INEXCLUDE_LIST, c4d.CUSTOMGUI_INEXCLUDE_LIST)
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
        if (id == INSTANTCE_ID_PROCESS_BTN):
            consider_dict = {
                "materials":    self.GetBool(INSTANTCE_ID_CONSIDER_MATERIALS),
                "normals":   self.GetBool(INSTANTCE_ID_CONSIDER_NORMALS),
                "uvs":          self.GetBool(INSTANTCE_ID_CONSIDER_UVS),
            }
            instance_args = {
                "precision":    self.GetBool(INSTANTCE_ID_PRECISION),
                "samples":      self.GetBool(INSTANTCE_ID_SAMPLES),
                "seed":         self.GetBool(INSTANTCE_ID_SEED),
                "blind":        self.GetBool(INSTANTCE_ID_BLIND_MODE),
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


class InstantceCommand(c4d.plugins.CommandData):
    dialog = None

    def Execute(self, doc):
        if self.dialog is None:
            self.dialog = InstantceMainDialog()

        return self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID)
    
    def RestoreLayout(self, secret):
        if self.dialog is None:
            self.dialog = InstantceMainDialog()
        
        return self.dialog.Restore(PLUGIN_ID, secret)

if __name__=='__main__':
    plugin_dir = os.path.dirname(__file__)

    symbol_parser.parse_and_export_in_caller(plugin_dir)

    if not c4d.plugins.GeResource().Init(plugin_dir):
            raise RuntimeError(f"Could not access resource at {plugin_dir}")
    
    c4d.plugins.RegisterCommandPlugin(id=PLUGIN_ID,
                                      str=IDS_INSTANTCE_NAME,
                                      info=0,
                                      help=IDS_INSTANTCE_HELP,
                                      dat=InstantceCommand(),
                                      icon=None)
