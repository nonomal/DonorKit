

import re
import os
encModel = os.getenv("PYTHONIOENCODING")


import mayashader
import maya.OpenMaya as OpenMaya






def getCildRoot (MDagPath):

    MFnDagNode = OpenMaya.MFnDagNode(MDagPath)
    if MFnDagNode.parentCount() > 0:

        parentMFnDagNode = OpenMaya.MFnDagNode(
            MFnDagNode.parent(0))
        parentPath = parentMFnDagNode.fullPathName()

        if len(parentPath) > 0:

            MSelectionList = OpenMaya.MSelectionList()
            OpenMaya.MGlobal.getSelectionListByName(
                parentPath,
                MSelectionList)

            if not MSelectionList.isEmpty():

                MDagPath = OpenMaya.MDagPath()
                MSelectionList.getDagPath(0, MDagPath)

                return getCildRoot( MDagPath )

        else:
            return MDagPath


def getRootList ():

    rootList = []

    MSelectionList = OpenMaya.MSelectionList()
    OpenMaya.MGlobal.getActiveSelectionList(MSelectionList)

    for index in xrange( MSelectionList.length() ):
        MObject = OpenMaya.MObject()
        MSelectionList.getDependNode(index, MObject)

        if MObject.apiType() in [
            OpenMaya.MFn.kMesh,
            OpenMaya.MFn.kTransform ]:

            MDagPath = OpenMaya.MDagPath()
            MSelectionList.getDagPath(index, MDagPath, MObject)

            OpenMaya.MGlobal.selectByName(
                MDagPath.fullPathName(),
                OpenMaya.MGlobal.kReplaceList )

            root = getCildRoot(MDagPath)
            if root not in rootList:
                rootList.append(root)

            break

    return rootList






def getChildren (MDagPath):

    childrenList = []

    MFnDagNode = OpenMaya.MFnDagNode(MDagPath)
    for index in xrange(MFnDagNode.childCount()):

        childMFnDagNode = OpenMaya.MFnDagNode(
            MFnDagNode.child(index))
        childPath = childMFnDagNode.fullPathName()

        MSelectionList = OpenMaya.MSelectionList()
        OpenMaya.MGlobal.getSelectionListByName(
            childPath,
            MSelectionList)

        if not MSelectionList.isEmpty():

            MDagPath = OpenMaya.MDagPath()
            MSelectionList.getDagPath(0, MDagPath)

            childrenList.append(MDagPath)
    
    return childrenList






def isDagSelected (MDagPath):

    MSelectionList = OpenMaya.MSelectionList()
    OpenMaya.MGlobal.getActiveSelectionList(MSelectionList)

    for index in xrange(MSelectionList.length()):
      
        matchMDagPath = OpenMaya.MDagPath()
        MSelectionList.getDagPath(index, matchMDagPath)

        if matchMDagPath == MDagPath:
            return True

    return False






def scan (tree=getRootList(), collector=[], selected=False):


    for treeDag in tree:

        treeObject = treeDag.node()

        treeName = treeDag.partialPathName().encode(encModel)
        treeType = treeObject.apiTypeStr().encode(encModel)

        attributes={}
        material = None


        # mark selected tree
        selectedFlag = False
        if not selected:
            selectedFlag = isDagSelected(treeDag)

        else:
            selectedFlag = True


        if selectedFlag:

            # get visibility attribute
            visibility =  OpenMaya.MFnDependencyNode(
                treeObject ).findPlug(
                    "visibility").asBool()
            attr = {"visibility": visibility}
            attributes.update(attr)


            
            if treeType == "kMesh":
                
                MFnMesh = OpenMaya.MFnMesh(treeDag)


                # get display color
                if MFnMesh.hasColorChannels(
                    MFnMesh.currentColorSetName() ):

                    MColorArray = OpenMaya.MColorArray()
                    MFnMesh.getColors(
                        MColorArray,
                        MFnMesh.currentColorSetName(),
                        OpenMaya.MColor(0,0,0,1))

                    color = list( MColorArray[0] )[:3]
                    for index in xrange(len(color)):
                        value = color[index]
                        color[index] = round(value, 4)

                    attr = {"displayColor": color}
                    attributes.update(attr)


                # get displacement bound
                shaders = OpenMaya.MObjectArray()
                MFnMesh.getConnectedShaders(0,
                    shaders, OpenMaya.MIntArray() )

                if shaders.length() > 0:

                    material = OpenMaya.MFnDependencyNode(shaders[0])

                    shaderPlug = material.findPlug("rman__displacement")
                    if shaderPlug.isConnected():

                        boundValue =  OpenMaya.MFnDependencyNode(
                            treeObject ).findPlug(
                                "rman_displacementBound").asFloat()
                        attr = {"rman_displacementBound": boundValue}
                        attributes.update(attr)


                # get subdivision scheme
                subdivScheme = "none"
                   
                mayaSubd = OpenMaya.MFnDependencyNode(
                    treeObject ).findPlug(
                        "displaySmoothMesh").asInt()
                rmanSubd = OpenMaya.MFnDependencyNode(
                    treeObject ).findPlug(
                        "rman_subdivScheme").asInt()

                if rmanSubd==1:
                    subdivScheme = "catmullClark"
                elif rmanSubd==2:
                    subdivScheme = "loop"
                elif rmanSubd==3:
                    subdivScheme = "bilinear"
                elif mayaSubd>=1:
                    subdivScheme = "catmullClark"

                attr = {"subdivScheme": subdivScheme}
                attributes.update(attr)

        

        # item description
        sItem = {
            "name": treeName,
            "type": re.sub(r"^k", "", treeType),
            "selected": selectedFlag,
            "attributes": attributes,
            "material": material,
            "children": []
        }

        collector.append(sItem)


        # next
        scan(
            tree=getChildren(treeDag),
            collector=sItem["children"],
            selected=selectedFlag )



    return collector






def clean (tree):

    treeClean=list()

    for item in tree:

        selected = item["selected"]
        children = item["children"]
            
        childClean = clean(children)

        if not children and selected:
            treeClean.append(item)

        elif childClean and children:
            item["children"] = childClean
            treeClean.append(item)

    return treeClean






def collectshaders (tree, collector={}):

    for item in tree:

        material = item["material"]
        if material:

            render  = mayashader.getPrmanNetwork(material)
            preview = mayashader.getPreviewNetwork(material)

            materialName = material.name().encode(encModel)
            collector[materialName] = dict(
                render=render,
                preview=preview )

        collectshaders(
            item["children"],
            collector )

    return collector






def getroot (tree, scope=[], path=None):

    for item in tree:

        _scope = [i for i in scope]

        name = item["name"]
        children = item["children"]
        selected = item["selected"]

        if not selected:
            _scope.append( name )

        else:
            root = os.path.join("/", *_scope)
            return os.path.join(root, name)

        path = getroot(children, scope=_scope)


    return path






def cut (tree):

    treeCut=list()

    for item in tree:

        treeCut = cut(item["children"])

        if item["selected"] :
            return [item]

    return treeCut






def get ():

    data = scan()
    data = clean(data)

    shaders=collectshaders(data)
    root=getroot(data)

    data = cut(data)

    return dict(
        data=data,
        shaders=shaders,
        root=root )






def show (treeItem, iteration=0):

    for item in treeItem:

        name = item["name"]
        typename = item["type"]
        selected = item["selected"]
        attributes = item["attributes"]
        material = item["material"]
        children = item["children"]

        ident = ""
        if iteration:
            ident = "    " * iteration

        print("{}name: {}".format(ident, name) )
        print("{}type: {}".format(ident, typename) )

        print("{}attributes:".format(ident) )
        if attributes:
            for key, value in attributes.items():
                print("{}  {}: {}".format(ident, key, value))

        print("{}selected: {}".format(ident, selected) )

        if material:
            materialName = material.name().encode(encModel)
            print("{}material: {}".format(ident, materialName) )
        print("\n")


        show(children, iteration=iteration+1)
