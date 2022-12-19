# -*- coding: utf-8 -*-
import json
import os
import oss2
import time
import logging
import zipfile
from oss2 import SizedFileAdapter, determine_part_size
from oss2.models import PartInfo
import subprocess


def handler(event, context):
    print(event)
    evt_lst = json.loads(event)
    evt = evt_lst['events'][0]
    bucket_name = evt['oss']['bucket']['name']
    object_name = evt['oss']['object']['key']
    print("bucket_name：", bucket_name)
    print("object_name:", object_name)
    file_type = os.path.splitext(object_name)[1]

    if file_type != ".zip":
        raise RuntimeError('{} filetype is not zip'.format(object_name))

    print("start to decompress zip file = {}".format(object_name))

    lst = object_name.split("/")
    zip_name = lst[-1]
    PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "")
    RETAIN_FILE_NAME = os.environ.get("RETAIN_FILE_NAME", "")
    if PROCESSED_DIR and PROCESSED_DIR[-1] != "/":
        PROCESSED_DIR += "/"
    if RETAIN_FILE_NAME == "false":
        newKeyPrefix = PROCESSED_DIR
    else:
        newKeyPrefix = PROCESSED_DIR + zip_name

    tmpWorkDir = "/mnt/auto/{}".format(context.request_id)
    print(tmpWorkDir)
    if not os.path.exists(tmpWorkDir):
        os.makedirs(tmpWorkDir)

    creds = context.credentials
    endpoint = 'oss-' + evt['region'] + '-internal.aliyuncs.com'
    auth = oss2.StsAuth(creds.access_key_id,
                        creds.access_key_secret, creds.security_token)
    bucket = oss2.Bucket(auth, endpoint, evt['oss']['bucket']['name'])
    bucket_object_name = bucket_name + "/" + object_name
    print("bucket_object_name:", bucket_object_name)
    tmpZipfile = "{}/{}".format(tmpWorkDir, zip_name)
    bucket.get_object_to_file(object_name, tmpZipfile)

    with zipfile.ZipFile(tmpZipfile) as zip_file:
        zip_list = zip_file.namelist()
        for f in zip_list:
            zip_file.extract(f, tmpWorkDir)

    print("解压完成")
    subprocess.check_call("rm -rf {}".format(tmpZipfile), shell=True)
    print("开始上传 ...")
    listDir(tmpWorkDir, bucket, newKeyPrefix)
    print("上传完毕")
    subprocess.check_call("rm -rf {}".format(tmpWorkDir), shell=True)


def listDir(destDir, bucket, newKeyPrefix):
    for filename in os.listdir(destDir):
        print("filename:", filename)
        pathname = os.path.join(destDir, filename)
        print("pathname:", pathname)
        if (os.path.isdir(pathname)):
            #print("is dir:", pathname)
            listDir(pathname, bucket, newKeyPrefix)
        else:
            #print("is file:", pathname)
            newkey = os.path.join(
                newKeyPrefix, "/".join(pathname.split("/")[4:]))
            print("newkey:", newkey)
            upload_part_object(pathname, newkey, bucket)

# 分片上传


def upload_part_object(filename, key, bucket):
    total_size = os.path.getsize(filename)
    # determine_part_size方法用于确定分片大小。
    part_size = determine_part_size(total_size, preferred_size=100 * 1024)
    upload_id = bucket.init_multipart_upload(key).upload_id
    parts = []

    # 逐个上传分片。
    with open(filename, 'rb') as fileobj:
        part_number = 1
        offset = 0
        while offset < total_size:
            num_to_upload = min(part_size, total_size - offset)
            # 调用SizedFileAdapter(fileobj, size)方法会生成一个新的文件对象，重新计算起始追加位置。
            result = bucket.upload_part(key, upload_id, part_number,
                                        SizedFileAdapter(fileobj, num_to_upload))
            parts.append(PartInfo(part_number, result.etag))

            offset += num_to_upload
            part_number += 1
    bucket.complete_multipart_upload(key, upload_id, parts, headers=dict())
    return "OK"
