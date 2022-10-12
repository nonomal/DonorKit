#!/usr/bin/env python



import os
import re

import toolkit.maya.mplug
import toolkit.maya.find
import toolkit.maya.attribute

from toolkit.usd import naming as nameMirror

from toolkit.core import Metadata
from toolkit.usd import read

import xml.etree.ElementTree as ET
import oslquery


import maya.cmds as mayaCommand
import maya.OpenMaya as OpenMaya





def getSelectionName ():

    selection = mayaCommand.ls( selection=True )
    if not selection: return

    material = selection[0]
    if mayaCommand.nodeType(material) == "shadingEngine":
        return material





class Manager (object):


    def __init__ (self, data=dict(), assets=dict()):
        
        self.RMAN_DEFAULTS = data
        self.ASSETS = assets



    def typeEditor (self, paramdefault, paramtype):

        if paramtype in ["color", "normal", "vector"]:
            return tuple([float(i) for i in paramdefault.split(" ")])

        elif paramtype == "float":
            paramdefault = paramdefault.replace("f", "")
            return float(paramdefault)

        elif paramtype == "int":
            return int(paramdefault)

        elif paramtype == "string":
            return str(paramdefault)



    def parseArgs (self, root, data=None):

        if data == None:
            data = dict()

        for child in root:
            if child.tag == "param":

                paramname = child.attrib["name"]
                paramtype = child.attrib["type"]

                paramdefault = None
                isDynamicArray = False

                for key in child.attrib:
                    if key == "isDynamicArray":
                        isDynamicArray = True
                    elif key == "default":
                        paramdefault = child.attrib["default"]

                if paramdefault and not isDynamicArray:
                    paramdefault = self.typeEditor(paramdefault, paramtype)

                    data[paramname] = dict(
                            type=paramtype,
                            default=paramdefault )

            data = self.parseArgs(child, data=data)
        
        return data



    def getShaderDefaults (self, shaderType):

        if shaderType not in self.RMAN_DEFAULTS:

            shaderData = dict()
            RMANTREE = os.getenv("RMANTREE", "")

            ArgsPath = os.path.join(
                os.path.join(RMANTREE, "lib", "plugins", "Args"),
                "{}.args".format(shaderType) )
                
            OslPath = os.path.join(
                os.path.join(RMANTREE, "lib", "shaders"),
                "{}.oso".format(shaderType) )

            if os.path.exists(ArgsPath):
                tree = ET.ElementTree(file=ArgsPath)
                root = tree.getroot()

                shaderData = self.parseArgs(root)
                self.RMAN_DEFAULTS[shaderType] = shaderData


            elif os.path.exists(OslPath):
                shader = oslquery.OslQuery()
                shader.open(OslPath)

                for index in range(shader.nparams()):
                    parameter = shader.getparam(index)

                    if not parameter["isoutput"]:
                        if not parameter["isstruct"]:

                            paramname = parameter["name"]
                            shaderData[paramname] = dict(
                                type=parameter["type"],
                                default=parameter["default"] )

                self.RMAN_DEFAULTS[shaderType] = shaderData

        else:
            shaderData = self.RMAN_DEFAULTS.get(shaderType, dict())

        return shaderData



    def getNetwork (self, shader, prman=True, collector={}):

        shaderType = shader.typeName()
        shaderName = str(shader.name())

        if not prman and shaderType not in [
                "usdPreviewSurface", "file", "place2dTexture"]:
            return collector

        if shaderName not in collector:
            inputs = dict()
            shaderData = dict(
                id=shaderType,
                inputs=inputs )

            assetID = self.getAssetID(shaderName)
            if assetID:
                shaderData["asset"] = assetID
            
            collector[shaderName] = shaderData

            if prman:
                shaderDefaults = self.getShaderDefaults(shaderType)

            for index in range(shader.attributeCount()):

                MObject = shader.attribute(index)
                attribute = OpenMaya.MFnAttribute(MObject)

                attrName = attribute.name()
                MPlug = shader.findPlug(attrName)


                if attribute.isWritable():

                    if MPlug.isConnected() and shaderType != "PxrManifold2D":

                        if not prman and attrName not in [
                                "diffuseColor", "metallic", "roughness",
                                "normal", "displacement", "opacity", "uvCoord"]:
                            continue

                        valueType = toolkit.maya.mplug.getAs( MPlug, asType=True )

                        if prman:
                            data = shaderDefaults.get(attrName, None)
                            if data != None:
                                valueType = data["type"]

                        MPlugSource = MPlug.source()
                        sourceNode = OpenMaya.MFnDependencyNode(
                            MPlugSource.node() )

                        if MPlugSource.info():

                            inputs[attrName] = dict(
                                value=MPlugSource.name().split("."),
                                type=valueType,
                                connection=True )
                            
                            collector = self.getNetwork(
                                sourceNode,
                                prman=prman,
                                collector=collector )


                    elif prman:
                        data = shaderDefaults.get(attrName, None)
                        value = toolkit.maya.mplug.getAs( MPlug, asValue=True )

                        if data != None and value != None:

                            valueDefault = data["default"]
                            valueType    = data["type"]

                            collectAttibue = False

                            if isinstance(value, float):
                                value = round(value, 4)

                            if isinstance(value, tuple) and isinstance(valueDefault, tuple):
                                if len(value) == len(valueDefault):

                                    for index in range( len(valueDefault) ):
                                        defaultComponent = valueDefault[index]

                                        if isinstance(defaultComponent, float):
                                            exponent = len(str(defaultComponent).split(".")[1])
                                            valueComponent = round(value[index], exponent)
                                            if valueComponent != defaultComponent:
                                                collectAttibue = True
                                                break
                                        elif value[index] != valueDefault[index]:
                                                collectAttibue = True
                                                break
                                    
                                    if collectAttibue:
                                        value = tuple(round(i, 4) for i in value)

                            elif value != valueDefault:
                                    collectAttibue = True


                            if collectAttibue:
                                inputs[attrName] = dict(
                                value=value,
                                type=valueType,
                                connection=False )



                    elif attrName in [
                            "diffuseColor", "emissiveColor", "opacity",
                            "ior", "metallic", "roughness", "clearcoat",
                            "clearcoatRoughness", "fileTextureName",
                            "colorSpace" ] and not MPlug.isDefaultValue():

                        value = toolkit.maya.mplug.getAs(MPlug, asValue=True)
                        if value != None:
                            typeString = toolkit.maya.mplug.getAs(MPlug, asType=True)

                            inputs[attrName] = dict(
                                value=value,
                                type=typeString,
                                connection=False )

                    elif shaderType == "place2dTexture" and attrName in [
                            "repeatUV", "rotateUV", "offset"]:

                        value = toolkit.maya.mplug.getAs(MPlug, asValue=True)
                        if value != None:
                            typeString = toolkit.maya.mplug.getAs(MPlug, asType=True)

                            inputs[attrName] = dict(
                                value=value,
                                type=typeString,
                                connection=False )


        return collector



    def getPrmanNetwork (self, shaderGroup):

        inputs = dict()

        material = dict(
            material=dict(
                name=str(shaderGroup.name()),
                inputs=inputs ),
            shaders=dict())

        for connection in [
            "displacement",
            "surface" ]:

            attrName = "rman__" + connection
            shaderPlug = shaderGroup.findPlug(attrName)
            if shaderPlug.isConnected():
                connectionSource = shaderPlug.source()

                inputs[attrName] = connectionSource.name().split(".")
                    
                shader = OpenMaya.MFnDependencyNode(
                    connectionSource.node() )

                material["shaders"] = self.getNetwork(
                    shader, prman=True,
                    collector=material.get("shaders") )

        return material



    def getHydraNetwork (self, shaderGroup):

        inputs = dict()

        material = dict(
            material=dict(
                name=str(shaderGroup.name()),
                inputs=inputs ),
            shaders=dict())

        attrName = "surfaceShader"
        shaderPlug = shaderGroup.findPlug(attrName)
        
        if shaderPlug.isConnected():
            connectionSource = shaderPlug.source()

            inputs[attrName] = connectionSource.name().split(".")

            shader = OpenMaya.MFnDependencyNode(
                connectionSource.node() )

            network = self.getNetwork(
                shader, prman=False,
                collector=material.get("shaders") )

        return material



    def makeUsdScheme (self, data, renderer, inherit=False):

        data = self.applyUsdNaming(data)
        if renderer == "hydra":
            data["shaders"] = self.editHydraNetwork(
                data.get("shaders", {}))
        elif renderer == "prman":
            data["shaders"] = self.editPrmanNetwork(
                data.get("shaders", {}))


        if not inherit: return data
        data = self.groupReferences(data)


        shaders = data.get("shaders", {})
        references = data.get("references", {})

        lostConnections = dict()
        for ID, schemeRef in references.items():

            scheme = self.ASSETS.get(ID, {})
            schemeUsd = scheme.get(renderer, {})

            assetName = schemeUsd.get("name")
            assetPath = schemeUsd.get("path")
            if not assetPath:
                continue

            schemeRef["name"] = assetName
            schemeRef["path"] = assetPath

            overrideShaders = dict()
            shadersUsd = schemeUsd.get("shaders", {})
            shadersRef = schemeRef.get("shaders", {})

            # block reference node
            # with name used for new one
            for nodeName in shadersUsd:
                if nodeName in shaders:
                    overrideShaders[nodeName] = None

            # find out overrides
            for nodeName, specRef in shadersRef.items():
                specUsd = shadersUsd.get(nodeName, {})

                idUsd = specUsd.get("id", {})
                idRef = specRef.get("id", {})

                inputsUsd = specUsd.get("inputs", {})
                inputsRef = specRef.get("inputs", {})

                # mark node as inactive
                if idRef != idUsd:
                    overrideShaders[nodeName] = None
                    lostConnections[nodeName] = dict(
                        id=idRef, inputs=inputsRef)
                    continue

                # find changed values
                overrideInputs = dict()
                for inplug, inputRef in inputsRef.items():
                    inputUsd = inputsUsd.get(inplug, {})

                    if inplug in inputsUsd:
                        inputsUsd.pop(inplug)

                    connectionRef = inputRef.get("connection")
                    connectionUsd = inputUsd.get("connection")

                    valueRef = inputRef.get("value")
                    valueUsd = inputUsd.get("value")

                    if type(valueRef) in [tuple, list]:
                        if not connectionRef:
                            valueRef = [round(i, 4) for i in valueRef]
                    elif type(valueRef) == float:
                        valueRef = round(valueRef, 4)

                    if type(valueUsd) in [tuple, list]:
                        if not connectionUsd:
                            valueUsd = [round(i, 4) for i in valueUsd]
                    elif type(valueUsd) == float:
                        valueUsd = round(valueUsd, 4)

                    hasChanges = False
                    if connectionRef != connectionUsd:
                        hasChanges = True
                    elif valueRef != valueUsd:
                        hasChanges = True

                    if hasChanges:
                        overrideInputs[inplug] = inputRef


                # if attribute go back to its defaults
                for usdInput in inputsUsd:
                    mayaInput = nameMirror.mayaInput(idRef, usdInput)
                    MFnDependencyNode = toolkit.maya.find.shaderByName(nodeName)

                    MPlug = MFnDependencyNode.findPlug(mayaInput)
                    overrideInputs[usdInput] = self.getMPlugSpec(MPlug)


                if overrideInputs:
                    overrideShaders[nodeName] = dict(
                        id=None, inputs=overrideInputs)

            schemeRef["shaders"] = overrideShaders


        # create new node for referenced one with changed type
        for nodeName, nodeSpec in lostConnections.items():
            shaders[nodeName] = nodeSpec

        # update lost connections
        for nodeName in lostConnections:
            dataUpdate = self.getOutputData(nodeName)
            for ID, schemeUpdate in dataUpdate.items():

                shadersUpdate = schemeUpdate.get("shaders", {})
                for nodeNameUpdate, specUpdate in shadersUpdate.items():
                    if nodeNameUpdate in shaders:
                        continue

                    schemeRef = references.get(ID, {})
                    references[ID] = schemeRef

                    shadersRef = schemeRef.get("shaders", {})
                    schemeRef["shaders"] = shadersRef

                    specRef = shadersRef.get(nodeNameUpdate, {})
                    shadersRef[nodeNameUpdate] = specRef

                    inputsRef = specRef.get("inputs", {})
                    specRef["inputs"] = inputsRef

                    inputsUpdate = specUpdate.get("inputs", {})
                    for plugName, plugSpec in inputsUpdate.items():
                        inputsRef[plugName] = plugSpec


        return data



    def getMPlugSpec (self, MPlug):

        valueType = toolkit.maya.mplug.getAs(MPlug, asType=True)

        if not MPlug.isConnected():
            return dict(
                value=toolkit.maya.mplug.getAs(MPlug, asValue=True),
                type=valueType,
                connection=False)
        else:

            nodeName, mayaOutput = MPlug.source().name().split(".")
            Shader = toolkit.maya.find.shaderByName(nodeName)

            usdOutput = nameMirror.usdOutput(
                Shader.typeName(), mayaOutput)

            return dict(
                value=[nodeName, usdOutput],
                type=valueType,
                connection=True)



    def getOutputData (self, nodeName):

        data = dict()

        MFnDependencyNode = toolkit.maya.find.shaderByName(nodeName)
        for index in range(MFnDependencyNode.attributeCount()):

            MFnAttribute = OpenMaya.MFnAttribute(
                MFnDependencyNode.attribute(index))
            MPlug = MFnDependencyNode.findPlug(
                MFnAttribute.name())

            if MFnAttribute.isHidden() or not MPlug.isConnected():
                continue

            MPlugArray = OpenMaya.MPlugArray()
            MPlug.destinations(MPlugArray)
            for index in range(MPlugArray.length()):
                MPlugDest = MPlugArray[index]

                nodeDest = OpenMaya.MFnDependencyNode(
                    MPlugDest.node() )
                if nodeDest.typeName() == "shadingEngine":
                    continue
                if not nodeDest.hasAttribute("assetID"):
                    continue

                ID = nodeDest.findPlug("assetID").asString()
                nodeName, mayaInput = MPlugDest.name().split(".")

                dataReference = data.get(ID, {})
                data[ID] = dataReference

                dataShaders = dataReference.get("shaders", {})
                dataReference["shaders"] = dataShaders

                dataNode = dataShaders.get(nodeName, {})
                dataShaders[nodeName] = dataNode

                dataInputs = dataNode.get("inputs", {})
                dataNode["inputs"] = dataInputs

                usdInput = nameMirror.usdInput(
                    nodeDest.typeName(), mayaInput)

                dataInputs[usdInput] = self.getMPlugSpec(MPlugDest)

        return data



    def applyUsdNaming (self, data):


        def getShaderID (name):
            Shader = toolkit.maya.find.shaderByName(name)
            return Shader.typeName()


        inputs = dict()
        material = data.get("material", {})
        inputsMaterial = material.get("inputs", {})
        for mayaInput, inputValue in inputsMaterial.items():
            nodeName, mayaOutput = inputValue
            usdInput = nameMirror.usdInput("shadingEngine", mayaInput)
            usdOutput = nameMirror.usdOutput(
                getShaderID(nodeName), mayaOutput)
            inputs[usdInput] = [nodeName, usdOutput]
        material["inputs"] = inputs


        shadersBuffer = dict()
        shaders = data.get("shaders", {})
        for nameShader, specShader in shaders.items():
            mayaID = specShader.get("id")
            usdID = nameMirror.usdID(mayaID)
            if usdID == None: continue

            inputs = dict()
            inputsShader = specShader.get("inputs")
            for mayaInput, specInput in inputsShader.items():
                usdInput = nameMirror.usdInput(mayaID, mayaInput)

                value = specInput.get("value")
                valueType = specInput.get("type")
                connection = specInput.get("connection")
                if connection:
                    nodeName, mayaOutput = specInput.get("value")
                    usdOutput = nameMirror.usdOutput(
                        getShaderID(nodeName), mayaOutput)
                    value = [nodeName, usdOutput]
                inputs[usdInput] = dict(
                    value=value,
                    type=valueType,
                    connection=connection )

            buffer = dict(id=usdID,inputs=inputs)
            assetID = specShader.get("asset", None)
            if assetID != None:
                buffer["asset"] = assetID
            shadersBuffer[nameShader] = buffer

        data["shaders"] = shadersBuffer


        return data



    def editHydraNetwork (self, data):

        units = 0.01           # UNIT DEPEND
        dataPrimvar = None

        for nameShader, specShader in data.items():
            nodeID = specShader.get("id")

            if nodeID == "UsdPreviewSurface":
                inputs = specShader.get("inputs", {})
                for nameInput, specInput in inputs.items():
                    if not specInput.get("connection"):
                        continue
                    
                    childName = specInput.get("value")[0]
                    childShader = data.get(childName, None)
                    if childShader == None: continue
                    data[childName] = childShader

                    childInputs = childShader.get("inputs", {})
                    childShader["inputs"] = childInputs

                    # add scale and offset for displacement texutre
                    if nameInput == "displacement":

                        childInputs["bias"] = dict(
                            value=list([round(-0.5*units,4)]*4),
                            type="float4",
                            connection=False )
                        childInputs["scale"] = dict(
                            value=list([round(1.0*units,4)]*4),
                            type="float4",
                            connection=False )

                    # apply color space rules
                    ocioConfig = os.getenv("OCIO")
                    if not ocioConfig:
                        if "sourceColorSpace" in childInputs:
                            childInputs.pop("sourceColorSpace")
                        continue

                    colorSpace = childInputs.get("sourceColorSpace")
                    if not colorSpace:
                        continue

                    value = colorSpace.get("value")
                    if nameInput == "diffuseColor" and value in ["acescg"]:
                        value = "sRGB"
                    elif nameInput in ["displacement", "normal"]:
                        value = "raw"
                    else:
                        value = "auto"
                    colorSpace["value"] = value
            
            elif nodeID == "UsdUVTexture":
                inputs = specShader.get("inputs", {})
                inputs["wrapS"] = dict(
                    connection=False, 
                    type="token", 
                    value="repeat")
                inputs["wrapT"] = dict(
                    connection=False, 
                    type="token", 
                    value="repeat")
            
            elif nodeID == "UsdTransform2d":
                nodePrimvar = f"{nameShader}Primvar"

                dataItem = dict(
                    id="UsdPrimvarReader_float2",
                    inputs=dict(
                        varname=dict(
                            connection=False, 
                            type="token", 
                            value="st" )))
                assetID = specShader.get("asset", None)
                if assetID != None:
                    dataItem["asset"] = assetID
                dataPrimvar = dict()
                dataPrimvar[nodePrimvar] = dataItem

                inputs = specShader.get("inputs", {})
                inputs["in"] = dict(
                    connection=True, 
                    type="float2", 
                    value=[nodePrimvar, "result"])

        if dataPrimvar != None:
            data.update(dataPrimvar)

        return data



    def editPrmanNetwork (self, data):

        units = 0.01           # UNIT DEPEND

        for nameShader, specShader in data.items():
            nodeID = specShader.get("id")

            if nodeID == "PxrDisplace":
                MFnDependencyNode = toolkit.maya.find.shaderByName(nameShader)
                MPlug = MFnDependencyNode.findPlug("dispAmount")
                specInput = self.getMPlugSpec(MPlug)

                if not specInput.get("connection"):
                    specInput["value"] = round(
                        specInput.get("value") * units, 4)
                    specShader["inputs"]["dispAmount"] = specInput

            elif nodeID == "PxrRoundCube":
                MFnDependencyNode = toolkit.maya.find.shaderByName(nameShader)
                MPlug = MFnDependencyNode.findPlug("frequency")
                specInput = self.getMPlugSpec(MPlug)

                if not specInput.get("connection"):
                    specInput["value"] = round(
                        specInput.get("value") / units, 4)
                    specShader["inputs"]["frequency"] = specInput

        return data



    def groupReferences (self, data):
        
        references = dict()
        shaders    = dict()

        for name, spec in data.get("shaders").items():
            
            ID = spec.get("asset")
            if not ID:
                shaders[name] = spec
                continue
            
            scheme = self.getAssetScheme(ID)
            if not scheme:
                shaders[name] = spec
                continue

            reference = references.get(ID, {})
            references[ID] = reference

            overrides = reference.get("shaders", {})
            reference["shaders"] = overrides

            if name not in overrides:
                overrides[name] = dict(
                    id=spec.get("id"),
                    inputs=spec.get("inputs"))

        data["references"] = references
        data["shaders"]    = shaders

        return data



    def getAssetID (self, node):

        if mayaCommand.attributeQuery(
                "assetID", node=node, exists=True):
            return mayaCommand.getAttr(f"{node}.assetID")



    def getAssetScheme (self, ID):

        if ID in self.ASSETS:
            return self.ASSETS[ID]

        path = Metadata.findMaterial(ID)
        if not path: return

        prman, hydra = dict(), dict()
        for pathRef in read.asReferences(path):

            if re.match(r".*RenderMan\.usd[ac]*$", pathRef):
                prman = read.asUsdBuildScheme(pathRef)
                prman["name"] = read.asDefaultPrim(pathRef)
                prman["path"] = pathRef

            elif re.match(r".*Hydra\.usd[ac]*$", pathRef):
                hydra = read.asUsdBuildScheme(pathRef)
                hydra["name"] = read.asDefaultPrim(pathRef)
                hydra["path"] = pathRef

        scheme = dict(prman=prman, hydra=hydra)
        self.ASSETS[ID] = scheme

        return scheme



    def getBuildScheme (self, shaderGroup):

        prman = self.getPrmanNetwork(shaderGroup)
        hydra = self.getHydraNetwork(shaderGroup)

        return dict(prman=prman, hydra=hydra)



    def getUsdBuildScheme (self, shaderGroup, inherit=False):

        data = self.getBuildScheme(shaderGroup)

        prman = self.makeUsdScheme(
            data.get("prman"), "prman", inherit)
        hydra = self.makeUsdScheme(
            data.get("hydra"), "hydra", inherit)

        return dict(prman=prman, hydra=hydra)
