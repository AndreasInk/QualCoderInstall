# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import logging
import os
from random import randint
import sqlite3
import sys
import traceback

from PyQt6 import QtWidgets

from .color_selector import colors

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)


class RqdaImport:
    """ Import an RQDA database into a new QualCoder database. """

    parent_textEdit = None
    app = None
    conn = None

    def __init__(self, app, parent_textedit):
        super(RqdaImport, self).__init__()

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textedit

        self.file_path, ok = QtWidgets.QFileDialog.getOpenFileName(None,
                                                                   _('Select RQDA file'),
                                                                   self.app.settings['directory'], "*.rqda")
        if not ok or self.file_path == "":
            return
        self.conn = sqlite3.connect(self.file_path)
        self.parent_textEdit.append(_("Beginning import from RQDA"))
        try:
            self.import_data()
            self.parent_textEdit.append(_("Data imported from ") + self.file_path)
            self.parent_textEdit.append(_("File categories are not imported from RQDA"))
        except Exception as e:
            self.parent_textEdit.append(_("Data import unsuccessful from ") + self.file_path + "\n" + str(e))

    @staticmethod
    def convert_date(r_date):
        """ Convert RQDA date format from:
        Mon Oct 28 08:11:36 2019 to: yyyy-mm-dd hh:mm:ss
        Mon Oct 28 8:11:36 2019 to: yyyy-mm-dd hh:mm:ss
        RQDA does have a leading space for single digit days.
        RQDA does had 2 digit dates e.g. '12' '09'
        Fri Dec  6 09:26:07 2019

        TODO some dates are like this after rqda conversion: 2019-03- 1 17:51:21
        TODO original RQDA date:  Fri Mar  1 17:51:21 2019

        param: rqda formatted date
        return: standard format date
        """

        yyyy = r_date[-4:]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        mm = str(months.index(r_date[4:7]) + 1)
        if len(mm) == 1:
            mm = "0" + mm
        # Day can have a leading space, so '12' or ' 9'
        dd = r_date[8:10]
        if dd[0] == " ":
            dd = "0" + dd[1]
        # Hours is always 2 digits
        # Different way to get hh ,mm ss as slice was not working
        s = r_date.split(" ")
        # The first minus space is between time and year, the second minus space between date and time
        hh_mm_ss = s[-2]
        return yyyy + "-" + mm + "-" + dd + " " + hh_mm_ss

    def import_data(self):
        """ Code colours are randomly created.
         The codername in qualcoder settings is set to the first owner found in RQDA.

         Note sqlite3.Integrity error can occur if he same text is coded by the same code and same owner.
         So adding a check for this. """

        r_cur = self.conn.cursor()
        q_cur = self.app.conn.cursor()
        r_cur.execute("select memo from project")
        res = r_cur.fetchone()
        q_cur.execute("update project set memo=?", (res[0],))
        if res[0] is not None:
            self.parent_textEdit.append(_("Project memo imported"))
        r_cur.execute("select id,name, file, memo, owner, date from source")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            q_cur.execute("insert into source (id, name, fulltext,memo, owner, date, mediapath) values (?,?,?,?,?,?,?)",
                          [r[0], r[1], r[2], r[3], r[4], self.convert_date(r[5]), None])
            i += 1
        self.parent_textEdit.append(str(i) + _(" files imported"))
        r_cur.execute("select fid,position,annotation, owner, date from annotation")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            if r[3] != "" and r[3] is not None:
                q_cur.execute("insert into annotation (fid, pos0, pos1, memo, owner, date) values (?,?,?,?,?,?)",
                              [r[0], r[1], r[1] + 1, r[2], r[3], self.convert_date(r[4])])
                i += 1
        self.parent_textEdit.append(str(i) + _(" annotations imported"))
        r_cur.execute("select name,journal, owner, date from journal")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            q_cur.execute("insert into journal (name, jentry, owner, date) values (?,?,?,?)",
                          [r[0], r[1], r[2], self.convert_date(r[3])])
            i += 1
        self.parent_textEdit.append(str(i) + _(" journals imported"))
        r_cur.execute("select id, name, memo, owner, date from cases")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            try:
                q_cur.execute("insert into cases (caseid, name, memo, owner, date) values (?,?,?,?,?)",
                              [r[0], r[1], r[2], r[3], self.convert_date(r[4])])
                i += 1
            except sqlite3.IntegrityError:
                pass
        self.parent_textEdit.append(str(i) + _(" cases imported"))
        r_cur.execute("select catid, name, memo, owner, date from codecat")
        res = r_cur.fetchall()
        i = 0  # Do not use enumerate as res could be None
        for r in res:
            # There are no supercatids in rqda
            try:
                q_cur.execute("insert into code_cat (catid,name, memo, owner, date,supercatid) values (?,?,?,?,?,?)",
                              [r[0], r[1], r[2], r[3], self.convert_date(r[4]), None])
                i += 1
            except sqlite3.IntegrityError:
                pass
        self.parent_textEdit.append(str(i) + _(" code categories imported"))
        # get catids for each code cid
        r_cur.execute("select cid, catid from treecode")
        treecodes = r_cur.fetchall()
        r_cur.execute("select id, name, memo,color, owner, date from freecode")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            code_color = colors[randint(0, len(colors) - 1)]
            treecode = None
            for t in treecodes:
                if t[0] == r[0]:
                    treecode = t[1]  # the corresponding catid
            try:
                q_cur.execute("insert into code_name (cid, catid,name, memo,color, owner, date) values (?,?,?,?,?,?,?)",
                              [r[0], treecode, r[1], r[2], code_color, r[4], self.convert_date(r[5])])
                i += 1
            except sqlite3.IntegrityError:
                pass
        self.parent_textEdit.append(str(i) + " codes imported")
        r_cur.execute("select cid, fid, seltext,selfirst,selend,memo, owner, date from coding")
        res = r_cur.fetchall()
        i = 0
        dup = 0
        for r in res:
            if r[2] != "" and r[2] is not None:
                try:
                    q_cur.execute(
                        "insert into code_text (cid, fid,seltext, pos0,pos1,memo, owner, date) values (?,?,?,?,?,?,?,?)",
                        [r[0], r[1], r[2], r[3], r[4], r[5], r[6], self.convert_date(r[7])])
                    i += 1
                except sqlite3.IntegrityError:
                    dup += 1
        self.parent_textEdit.append(str(i) + _(" codings imported"))
        if dup > 0:
            self.parent_textEdit.append(str(dup) + _(" duplicated codings found and ignored"))
        r_cur.execute("select cid, fid, seltext,selfirst,selend,memo, owner, date from coding2")
        res = r_cur.fetchall()
        i = 0
        dup = 0
        for r in res:
            if r[2] != "" and r[2] is not None:
                try:
                    q_cur.execute(
                        "insert into code_text (cid, fid,seltext, pos0,pos1,memo, owner, date) values (?,?,?,?,?,?,?,?)",
                        [r[0], r[1], r[2], r[3], r[4], r[5], r[6], self.convert_date(r[7])])
                    i += 1
                except sqlite3.IntegrityError:
                    dup += 1
        self.parent_textEdit.append(str(i) + _(" codings imported from coding2 table"))
        if dup > 0:
            self.parent_textEdit.append(str(dup) + _(" duplicated codings found and ignored from coding2 table"))
        # attribute class = character or numeric
        r_cur.execute("select distinct variable from caseAttr")
        case_attr = r_cur.fetchall()
        r_cur.execute("select name,class,memo, owner, date from attributes")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            # default to a file attribute unless it is a case attribute
            case_or_file = "file"
            for c in case_attr:
                if c[0] == r[0]:
                    case_or_file = "case"
            try:
                q_cur.execute(
                    "insert into attribute_type (name, valuetype,caseOrFile,memo, owner, date) values (?,?,?,?,?,?)",
                    [r[0], r[1], case_or_file, r[2], r[3], self.convert_date(r[4])])
                i += 1
            except sqlite3.IntegrityError:
                pass
        self.parent_textEdit.append(str(i) + _(" attribute types imported"))
        r_cur.execute("select variable, value, caseID, owner, date from caseAttr")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            try:
                q_cur.execute("insert into attribute (name,value, id, owner,date, attr_type) values(?,?,?,?,?,?)",
                              [r[0], r[1], r[2], r[3], self.convert_date(r[4]), "case"])
                i += 1
            except sqlite3.IntegrityError:
                pass
        self.parent_textEdit.append(str(i) + _(" case attribute values imported"))
        r_cur.execute("select variable, value, fileID, owner, date from fileAttr")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            try:
                q_cur.execute("insert into attribute (name,value, id, owner,date, attr_type) values(?,?,?,?,?,?)",
                              [r[0], r[1], r[2], r[3], self.convert_date(r[4]), "file"])
                i += 1
            except sqlite3.IntegrityError:
                pass
        self.parent_textEdit.append(str(i) + _(" file attribute values imported"))
        r_cur.execute("select caseid,fid,selfirst,selend, owner, memo,date from caselinkage")
        res = r_cur.fetchall()
        i = 0
        for r in res:
            try:
                q_cur.execute("insert into case_text (caseid,fid,pos0,pos1,owner,memo, date) values(?,?,?,?,?,?,?)",
                              [r[0], r[1], r[2], r[3], r[4], r[5], self.convert_date(r[6])])
                i += 1
            except sqlite3.IntegrityError:
                pass
        self.parent_textEdit.append(str(i) + _(" case linked texts imported"))
        self.app.conn.commit()

        # Keep a copy of the text sources in the QualCoder documents folder
        r_cur.execute("select name, file from source")
        res = r_cur.fetchall()
        for r in res:
            name = r[0]
            if name[:-4] in (".pdf", ".odt", ".htm"):
                name = name[:-4] + ".txt"
            if name[:-5] in (".html", ".docx"):
                name = name[:-5] + ".txt"
            destination = self.app.project_path + "/documents/" + name
            f = open(destination, 'w')
            f.write(r[1])
            f.close()
            logger.info("Text file exported to " + destination)
        # Change the user name to the owner name from RQDA
        sql = "select owner from code_text"
        q_cur.execute(sql)
        result = q_cur.fetchone()
        if result is None:
            return
        self.app.settings['codername'] = result[0]
        self.app.write_config_ini(self.app.settings)


"""
RQDA database format
project (databaseversion text, date text,dateM text, memo text,about text, imageDir text
source (name text, id integer, file text, memo text, owner text, date text, dateM text, status integer
annotation (fid integer,position integer,annotation text, owner text, date text,dateM text, status integer
journal (name text, journal text, date text, dateM text, owner text,status integer
cases  (name text, memo text, owner text,date text,dateM text, id integer, status integer
codecat  (name text, cid integer, catid integer, owner text, date text, dateM text,memo text, status integer
coding  (cid integer, fid integer,seltext text, selfirst real, selend real, status integer, owner text, date text, memo text
coding2  (cid integer, fid integer,seltext text, selfirst real, selend real, status integer, owner text, date text, memo text
freecode  (name text, memo text, owner text,date text,dateM text, id integer, status integer, color text
treecode  (cid integer, catid integer, date text, dateM text, memo text, status integer, owner text
attributes (name text, status integer, date text, dateM text, owner text,memo text, class text
fileAttr (variable text, value text, fileID integer, date text, dateM text, owner text, status integer
caseAttr (variable text, value text, caseID integer, date text, dateM text, owner text, status integer
caselinkage  (caseid integer, fid integer, selfirst real, selend real, status integer, owner text, date text, memo text

treefile  (fid integer, catid integer, date text,dateM text, memo text, status integer,owner text
filecat  (name text,fid integer, catid integer, owner text, date text, dateM text,memo text, status integer
 """
