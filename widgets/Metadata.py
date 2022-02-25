#!/usr/bin/env python



import os
from . import tools






NAME = ".metadata.json"







class Metadata (object):


    def __init__ (self, path, metatype):

        self.default_data=dict()

        if metatype == "root":
            self.default_data = dict(
                info="",
                name=os.path.basename(path),
                type="root" )

        elif metatype == "usdasset":
            self.default_data = dict(
                info="",
                published=tools.getTimeCode(),
                type="usdasset",
                comments=dict(),
                status="WIP" )


        self.path = os.path.join(
            path, NAME)

        if not os.path.exists(self.path):
            self.default_settings(self.path)

        elif not tools.validJSON(self.path):
            self.default_settings(self.path)


    def default_settings (self, path):
        tools.datawrite(path, self.default_data)


    def load (self):

        data = tools.dataread(self.path)
        dataType = data.get("usdasset", "")

        if dataType == "usdasset":
            if not data.get("comments", ""):
                data["comments"] = dict()

        return data


    def save (self, data):
        tools.datawrite(self.path, data)







class MetadataManager (object):


    def __init__ (self, path, metatype):

        self.path = path
        self.metatype = metatype


    def __enter__(self):

        self.data = Metadata(self.path, self.metatype).load()
        return self.data


    def __exit__(self, exc_type, exc_val, exc_tb):

        Metadata(self.path, self.metatype).save(self.data)
