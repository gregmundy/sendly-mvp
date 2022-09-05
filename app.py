import json
import os
import sys
import re
import boto3
from uuid import uuid4
from base64 import b64decode
from flask import Flask
from flask_restful import Resource, Api, request
from sendgrid.helpers.inbound.config import Config
from sendgrid.helpers.inbound.parse import Parse

app = Flask(__name__)
api = Api(app)
config = Config()

if not os.path.exists("config.json"):
    print("No config.json found.")
    sys.exit(1)

with open("config.json", "r") as fh:
    creds = json.load(fh)


class InboundMessage(Resource):
    def get(self):
        return {"status": "ok"}

    def post(self):
        parse = Parse(config, request)
        tags = set(re.findall("#(\w+)", parse.payload["text"]))
        uuid = str(uuid4())

        if len(tags) == 0:
            tags = ["uncategorized"]

        session = boto3.Session(
            aws_access_key_id=creds["aws_access_key_id"],
            aws_secret_access_key=creds["aws_secret_access_key"],
        )

        s3 = session.resource("s3")
        dynamodb = session.resource("dynamodb")

        table = dynamodb.Table("SendlyResources")
        tags_table = dynamodb.Table("SendlyTags")

        # Add tags to collection
        for tag in tags:
            tags_table.put_item(Item={"Tag": tag, "CollectionID": uuid})

        # Write attachments to database
        object = s3.Object("test-bucket-sendly", f"{uuid}_content.txt")
        object.put(Body=parse.payload["text"])

        table.put_item(Item={"Filename": "content.txt", "CollectionID": uuid})

        object = s3.Object("test-bucket-sendly", f"{uuid}_content.html")
        object.put(Body=parse.payload["html"])

        table.put_item(Item={"Filename": "content.html", "CollectionID": uuid})

        try:
            for attachment in parse.attachments():
                object = s3.Object(
                    "test-bucket-sendly", f"{uuid}_{attachment['file_name']}"
                )
                object.put(Body=b64decode(attachment["contents"]))
                table.put_item(
                    Item={"Filename": attachment["file_name"], "CollectionID": uuid}
                )
        except Exception as e:
            pass

        return "OK"


api.add_resource(InboundMessage, "/inbound")

if __name__ == "__main__":
    app.run(debug=True)
