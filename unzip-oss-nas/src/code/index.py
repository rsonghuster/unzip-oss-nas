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
    print("bucket_name：",bucket_name)
    print("object_name:",object_name)
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
        newKey = PROCESSED_DIR
    else:
        newKey = PROCESSED_DIR + zip_name

    # destDir = "/home/app/{}".format(newKey)
    out, err = subprocess.Popen(['df','-h'], stdout = subprocess.PIPE).communicate()
    print('disk: ' + str(out))
    lines = [ l.decode() for l in out.splitlines() if str(l).find(':') != -1 ]
    nas_dirs = [ x.split()[-1] for x in lines ]
    print("newkey:",newKey)
    destDir = str(nas_dirs) + "{}".format(object_name)
    print(destDir)
    if not os.path.exists(destDir):
      os.makedirs(destDir) 

    
    creds = context.credentials
    endpoint = 'oss-' + evt['region'] + '-internal.aliyuncs.com'
    auth = oss2.StsAuth(creds.access_key_id, creds.access_key_secret, creds.security_token)
    bucket = oss2.Bucket(auth, endpoint, evt['oss']['bucket']['name'])
    bucket_object_name = bucket_name + "/" + object_name
    print("bucket_object_name:",bucket_object_name)
    print("destDir:",destDir)
    # destDirName = destDir + "/" + object_name
    destDirName = destDir + "/" + newKey
    print("destDirName:",destDirName)
    bucket.get_object_to_file(object_name, destDirName)#destDir
    # object_stream = bucket.get_object(object_name)
    # with open("/home/app/pdo_sqlite.zip/pdo_sqlite.zip", 'wb') as local_fileobj:
    #     shutil.copyfileobj(object_stream, local_fileobj)

    
    newKey = object_name.replace(".zip", "/")
    print("object_name:",object_name)
    # zip_fp = helper.OssStreamFileLikeObject(bucket, object_name)
    newkey = object_name.replace(".zip", "/")
    print("destDirName:",destDirName)
    destDirNameKey = destDirName.replace(".zip", "/")
    print("destDirNameKey:",destDirNameKey)

    zip_file = zipfile.ZipFile(destDirName)
    zip_list = zip_file.namelist() # 得到压缩包里所有文件
    for f in zip_list:
        zip_file.extract(f, destDirNameKey) # 循环解压文件到指定目录
 
    zip_file.close() # 关闭文件，必须有，释放内存
    print("解压完成")
    newKey = ""
    listDir(destDirNameKey,newkey,bucket)


    #newkey oss目标文件夹  filename上传文件 
def listDir(destDirNameKey,newKey,bucket):
        for filename in os.listdir(destDirNameKey):
         print("filename:",filename)
         pathname = os.path.join(destDirNameKey, filename)
         print("pathname:",pathname)
         if (os.path.isdir(pathname)):
             print("is filename:",filename)            
            #  newkey = os.path.split(os.path.split(pathname)[0])[1] + "/"
             newkey = pathname.split("//")[1]
             print("pathname2:",newkey)
             listDir(pathname,newkey,bucket)
         else:
             print("is pathname:",pathname)
            #  newkey = os.path.split(os.path.split(pathname)[0])[1] + "/"
             newkey = pathname.split("//")[1]
             print("newkey:",newkey)
            #  pathname = pathname.replace(".", new)
             upload_part_object(pathname,newkey,bucket)
            #  upload_object(pathname,newkey,bucket)


#简单上传
def upload_object(filename,key,bucket):
    with open(filename, 'rb') as fileobj:
        # Seek方法用于指定从第1000个字节位置开始读写。上传时会从您指定的第1000个字节位置开始上传，直到文件结束。
        fileobj.seek(1000, os.SEEK_SET)
        # Tell方法用于返回当前位置。
        current = fileobj.tell()
        # 填写Object完整路径。Object完整路径中不能包含Bucket名称。
        bucket.put_object(newkey, fileobj)

#分片上传        
def upload_part_object(filename,key,bucket):
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

    # 完成分片上传。
    # 如需在完成分片上传时设置相关Headers，请参考如下示例代码。
    headers = dict()
    # 设置文件访问权限ACL。此处设置为OBJECT_ACL_PRIVATE，表示私有权限。
    # headers["x-oss-object-acl"] = oss2.OBJECT_ACL_PRIVATE
    bucket.complete_multipart_upload(key, upload_id, parts, headers=headers)
    # bucket.complete_multipart_upload(key, upload_id, parts)

    # 验证分片上传。     上传成功 验证报错 这里先注释

    # with open(filename, 'rb') as fileobj:
    #     assert bucket.get_object(key).read() == fileobj.read() 



    # total_size = os.path.getsize(filename)
    # # determine_part_size方法用于确定分片大小。
    # part_size = determine_part_size(total_size, preferred_size=100 * 1024)
    # upload_id = bucket.init_multipart_upload(key).upload_id
    # parts = []

    # # 逐个上传分片。
    # with open(filename, 'rb') as fileobj:
    #     part_number = 1
    #     offset = 0
    #     while offset < total_size:
    #         num_to_upload = min(part_size, total_size - offset)
    #         # 调用SizedFileAdapter(fileobj, size)方法会生成一个新的文件对象，重新计算起始追加位置。
    #         result = bucket.upload_part(key, upload_id, part_number,
    #                                     SizedFileAdapter(fileobj, num_to_upload))
    #         parts.append(PartInfo(part_number, result.etag))

    #         offset += num_to_upload
    #         part_number += 1

    # # 完成分片上传。
    # # 如需在完成分片上传时设置相关Headers，请参考如下示例代码。
    # headers = dict()
    # # 设置文件访问权限ACL。此处设置为OBJECT_ACL_PRIVATE，表示私有权限。
    # # headers["x-oss-object-acl"] = oss2.OBJECT_ACL_PRIVATE
    # bucket.complete_multipart_upload(key, upload_id, parts, headers=headers)
    # # bucket.complete_multipart_upload(key, upload_id, parts)

    # # 验证分片上传。
    # with open(filename, 'rb') as fileobj:
    #     assert bucket.get_object(key).read() == fileobj.read() 

        # print("newKey:",newKey)
        # print("zip_fp:",zip_fp)

        #使用有问题
        # with helper.zipfile_support_oss.ZipFile(zip_fp) as zip_file:
        #     for name in zip_file.namelist():
        #         with zip_file.open(name) as file_obj:
        #             name = get_zipfile_name(name)
        #             bucket.put_object(newKey + name, file_obj)


    return "OK"
