#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
#    Copyright (C) 2010  Juan Martín <android@nauj27.com>
#
#    This program can be distributed under the terms of the GNU GPL v3.
#    See the file COPYING.
#
#    v0.1-pre-alpha-wip
#

import os
import stat
import errno
import subprocess

import fuse
from fuse import Fuse


if not hasattr(fuse, '__version__'):
    raise RuntimeError, \
        "your fuse-py doesn't know of fuse.__version__, probably it's too old."

fuse.fuse_python_api = (0, 2)


class MyStat(fuse.Stat):

    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0


class AdbFuse(Fuse):

    def __init__(self, *args, **kw):
        fuse.Fuse.__init__(self, *args, **kw)

    def getattr(self, path):
        myStat = MyStat()

        if path == '/':
            myStat.st_mode = stat.S_IFDIR | 0755
            myStat.st_nlink = 2
        else:
            process = subprocess.Popen(
                ['adb', 'shell', 'stat', '-t', '"%s"' % path],
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
            )
            (out_data, err_data) = process.communicate()

            # remove the path from the output string
            out_data = out_data[len(path)+1:]
            out_data_array = out_data.split()

            if (len(out_data_array) == 14):
                myStat.st_size = int(out_data_array[0])
                myStat.st_mode = int(out_data_array[2], 16)
                myStat.st_uid = int(out_data_array[3])
                myStat.st_gid = int(out_data_array[4])
                myStat.st_dev = int(out_data_array[5], 16)
                myStat.st_ino = int(out_data_array[6])
                myStat.st_nlink = int(out_data_array[7])
                myStat.st_atime = int(out_data_array[10])
                myStat.st_mtime = int(out_data_array[11])
                myStat.st_ctime = int(out_data_array[12])

            else:
                return -errno.ENOENT

        return myStat

    def readdir(self, path, offset):
        process = subprocess.Popen(
            ['adb', 'shell', 'ls', '--color=none', "-1", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out_data, err_data) = process.communicate()
        for r in out_data.splitlines():
            yield fuse.Direntry(r)

    def open(self, path, flags):
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES

    def read(self, path, size, offset):
        local_path = '/dev/shm%s' % (path, )

        if not os.path.exists(local_path):
            process = subprocess.Popen(
                ['adb', 'pull', path, local_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            (out_data, err_data) = process.communicate()

        # Open the local file and return data
        f = open(local_path, 'r')
        f.seek(offset)
        buf = f.read(size)
        f.close()
        # Remove local temporary file??
        #os.unlink(local)
        return buf

    def readlink(self, path):
        process = subprocess.Popen(
            ['adb', 'shell', 'readlink', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (out_data, err_data) = process.communicate()

        return '.%s' % (out_data.split()[0], )

    def unlink(self, path):
        #(out_data, err_data) = process.communicate()
        process = subprocess.Popen(
            ['adb', 'shell', 'rm', '-f', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    def rmdir(self, path):
        #(out_data, err_data) = process.communicate()
        process = subprocess.Popen(
            ['adb', 'shell', 'rmdir', path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    def symlink(self, path, path1):
        #(out_data, err_data) = process.communicate()
        process = subprocess.Popen(
            ['adb', 'shell', 'ln', '-s', path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    def rename(self, path, path1):
        process = subprocess.Popen(
            ['adb', 'shell', 'mv', "." + path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def link(self, path, path1):
        process = subprocess.Popen(
            ['adb', 'shell', 'ln', "." + path, "." + path1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def chmod(self, path, mode):
        process = subprocess.Popen(
            ['adb', 'shell', 'chmod', "." + path, mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def chown(self, path, user, group):
        process = subprocess.Popen(
            ['adb', 'shell', 'chown', "." + path, user, group],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def mknod(self, path, mode, dev):
        #print "*** path: %s, mode: %s, dev: %s" % (path, mode, dev,)
        process = subprocess.Popen(
            #['adb', 'shell', 'mknod', "-m", mode, '".' + path + '"', dev],
            ['adb', 'shell', 'touch', '.' + path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def mkdir(self, path, mode):
        process = subprocess.Popen(
            ['adb', 'shell', 'mkdir', "." + path, mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

    def utime(self, path, times):
        process = subprocess.Popen(
            ['adb', 'shell', 'touch', "-d", times, "." + path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        #(out_data, err_data) = process.communicate()

def main():
    usage="""
Userspace adb filesystem

""" + Fuse.fusage
    server = AdbFuse(version="%prog " + fuse.__version__,
                     usage=usage,
                     dash_s_do='setsingle')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
