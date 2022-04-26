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

# https://medium.com/@shauryashivam38/how-to-make-a-wordcloud-in-python-feat-stylecloud-88cdae5fc8c9

import os
# sudo python3 -m pip install pydub
import pydub
# sudo python3 -m pip install SpeechRecognition
# works with wav and flac files, wav can be multiple formats, so convert all to flac
# need to have ffmpeg or avconv installed (tricky instillation on Windows)
import speech_recognition
import sys
import logging
import traceback

from PyQt6 import QtCore, QtWidgets, QtGui

from .helpers import Message, msecs_to_mins_and_secs
from .GUI.base64_helper import *
from .GUI.ui_speech_to_text import Ui_DialogSpeechToText

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    txt = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(txt)
    logger.error(_("Uncaught exception: ") + txt)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), txt)


class SpeechToText(QtWidgets.QDialog):
    """ Converts audio or video audio track to text using online services.
     Process involves converting the audio track to flac, then chunk.
     Each chunk is stored as temp.was in the .qualcoder folder and chunk by chunk
     converted to text. Each text chunk is preceeded with a time stamp.

     https://github.com/Uberi/speech_recognition/blob/master/reference/library-reference.rst
     """

    app = None
    text = ""
    filepath = None
    flac_filepath = None
    # IBM an RFC5646 language tag
    # Bing BCP-47 language tag
    # Google IETF language tag
    language = "en-US"  # default
    strings = []
    service = "google"  # Also wit.ai, bing, houndify, ibm
    # Do not use google_cloud, requires a file

    username_ibm = ""
    password_ibm = ""
    chunksize = 60000  # 60 seconds
    google_text = "Online free google translate service. Limited to 50 requests per day. Each request up to 60 seconds in size."

    def __init__(self, app, av_filepath):

        sys.excepthook = exception_handler
        self.app = app
        self.text = ""
        self.filepath = av_filepath
        # Initialize the speech recognition class
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_DialogSpeechToText()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        # Default is google free
        self.ui.comboBox_service.currentIndexChanged.connect(self.service_changed)
        self.ui.textEdit_notes.setText(self.google_text)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_start.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_start.pressed.connect(self.start_conversion)

    def service_changed(self):
        """ Default is google. Change to"""

        if self.ui.comboBox_service.currentText() == "Google":
            self.ui.label_id.setEnabled(False)
            self.ui.lineEdit_id.setEnabled(False)
            self.ui.label_key.setEnabled(False)
            self.ui.lineEdit_key.setEnabled(False)
            self.ui.label_language.setEnabled(True)
            self.ui.lineEdit_language.setEnabled(True)
            self.ui.textEdit_notes.setText(self.google_text)
        if self.ui.comboBox_service.currentText() == "Microsoft Bing Voice Recognition":
            self.ui.label_id.setEnabled(False)
            self.ui.lineEdit_id.setEnabled(False)
            self.ui.label_key.setEnabled(True)
            self.ui.lineEdit_key.setEnabled(True)
            self.ui.label_language.setEnabled(True)
            self.ui.lineEdit_language.setEnabled(True)
            self.ui.textEdit_notes.setText("Bing\nBing Voice Recognition API keys 32-character lowercase hexadecimal strings")
        if self.ui.comboBox_service.currentText() == "Wit.ai":
            self.ui.label_id.setEnabled(False)
            self.ui.lineEdit_id.setEnabled(False)
            self.ui.label_key.setEnabled(True)
            self.ui.lineEdit_key.setEnabled(True)
            self.ui.label_language.setEnabled(False)
            self.ui.lineEdit_language.setEnabled(False)
            self.ui.textEdit_notes.setText("Wit.ai\nWit.ai keys are 32-character uppercase alphanumeric strings")
        if self.ui.comboBox_service.currentText() == "Houndify":
            self.ui.label_id.setEnabled(True)
            self.ui.lineEdit_id.setEnabled(True)
            self.ui.label_key.setEnabled(True)
            self.ui.lineEdit_key.setEnabled(True)
            self.ui.label_language.setEnabled(False)
            self.ui.lineEdit_language.setEnabled(False)
            msg = "Houndify\nHoundify client IDs and keys are Base64-encoded strings\n"
            msg += "www.houndify.com"
            self.ui.textEdit_notes.setText(msg)
        if self.ui.comboBox_service.currentText() == "IBM Speech":
            self.ui.label_id.setEnabled(True)
            self.ui.lineEdit_id.setEnabled(True)
            self.ui.label_key.setEnabled(True)
            self.ui.lineEdit_key.setEnabled(True)
            self.ui.label_language.setEnabled(True)
            self.ui.lineEdit_language.setEnabled(True)
            msg = "IBM Speech to text\n"
            msg += "usernames are strings of the form XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX\n"
            msg += "passwords are mixed-case alphanumeric strings"
            self.ui.textEdit_notes.setText(msg)

    def start_conversion(self):
        """ Convert the A/V format th audio flac format.
        Obtain GUI settings for conversion.
        Then process audio in chunks using online service. """

        chunktext = self.ui.comboBox_chunksize.currentText()
        if chunktext == "30 seconds":
            self.chunksize = 30000
        else:
            self.chunksize = 60000
        self.convert_to_flac()
        if self.flac_filepath is not None:
            self.convert_to_text()
        else:
            Message(self.app, _("Processing error"), _("Cannot process file")).exec()
        for s in self.strings:
            self.text += s

    def convert_to_text(self):
        """
        based on:
        https://stackoverflow.com/questions/39232150/python-speech-recognition-error-converting-mp3-file
        """

        # Load flac file
        audio_file = pydub.AudioSegment.from_file(self.flac_filepath, "flac")
        lang = self.ui.lineEdit_language.text()
        if lang == "":
            lang = "en-US"
        service_id = self.ui.lineEdit_id.text()
        service_key = self.ui.lineEdit_key.text()

        def divide_chunks(audio_file_, chunksize):
            """ Split file into 30 or 60 second chunks. """

            for j in range(0, len(audio_file_), self.chunksize):
                yield audio_file[j:j + chunksize]
        '''# Specify that a silent chunk must be at least 1 second long
        # Consider a chunk silent if it's quieter than -16 dBFS. May adjust these values.
        # split on silence does not work well
        chunks = pydub.silence.split_on_silence(audio_file, min_silence_len=500, silence_thresh=-16)'''
        chunks = list(divide_chunks(audio_file, self.chunksize))
        self.ui.progressBar.setMaximum(len(chunks))
        qc_dir = os.path.expanduser('~') + '/.qualcoder'
        r = speech_recognition.Recognizer()
        # For each chunk, save as wav, then read and run through recognize_google()
        self.strings = []
        for i, chunk in enumerate(chunks):
            chunk.export(qc_dir + "/tmp.wav", format='wav')
            with speech_recognition.AudioFile(qc_dir + "/tmp.wav") as source:
                audio = r.record(source)
            self.ui.progressBar.setValue(i + 1)
            self.ui.label_process.setText(_("Converting chunk ") + str(i + 1) + " / " + str(len(chunks)))
            s = ""
            if self.service == "google":
                # Google limited to 50 requests per day
                try:
                    s = r.recognize_google(audio, language=lang)
                except speech_recognition.UnknownValueError:
                    s = _("UNINTELLIGIBLE AUDIO")
                    self.ui.label_process.setText(s)
                except speech_recognition.RequestError as e:
                    s = _("NO SERVICE RESULTS: ") + "{0}".format(e)
                    self.ui.label_process.setText(s)
            if self.service == "wit.ai":
                # Language is configured in the wit account
                try:
                    s = r.recognize_wit(audio, key=service_key)
                except speech_recognition.UnknownValueError:
                    s = _("UNINTELLIGIBLE AUDIO")
                    self.ui.label_process.setText(s)
                except speech_recognition.RequestError as e:
                    s = _("NO SERVICE RESULTS: ") + "{0}".format(e)
                    self.ui.label_process.setText(s)
            if self.service == "bing":
                try:
                    s = r.recognize_bing(audio, key=service_key, language=lang)
                except speech_recognition.UnknownValueError:
                    s = _("UNINTELLIGIBLE AUDIO")
                    self.ui.label_process.setText(s)
                except speech_recognition.RequestError as e:
                    s = _("NO SERVICE RESULTS: ") + "{0}".format(e)
                    self.ui.label_process.setText(s)
            if self.service == "houndify":
                # English only
                try:
                    s = r.recognize_houndify(audio, client_id=service_id, client_key=service_key)
                except speech_recognition.UnknownValueError:
                    s = _("UNINTELLIGIBLE AUDIO")
                    self.ui.label_process.setText(s)
                except speech_recognition.RequestError as e:
                    s = _("NO SERVICE RESULTS: ") + "{0}".format(e)
                    self.ui.label_process.setText(s)
            if self.service == "ibm":
                try:
                    s = r.recognize_ibm(audio, username=service_key, password=service_key, language=lang)
                except speech_recognition.UnknownValueError:
                    s = _("UNINTELLIGIBLE AUDIO")
                    self.ui.label_process.setText(s)
                except speech_recognition.RequestError as e:
                    s = _("NO SERVICE RESULTS: ") + "{0}".format(e)
                    self.ui.label_process.setText(s)
            ts = self.timestamp(i * self.chunksize)
            self.strings.append(ts + s)

    '''GOOGLE_CLOUD_SPEECH_CREDENTIALS = 
       r"""INSERT THE CONTENTS OF THE GOOGLE CLOUD SPEECH JSON CREDENTIALS FILE HERE"""
    print("Google Cloud Speech " + r.recognize_google_cloud(audio, credentials_json=GOOGLE_CLOUD_SPEECH_CREDENTIALS))
    '''

    def timestamp(self, time_msecs):
        """ timestamp using current format.
        Format options:
        [mm.ss], [mm:ss], [hh.mm.ss], [hh:mm:ss],
        {hh.mm.ss}, #hh:mm:ss.sss#
        """

        fmt = self.app.settings['timestampformat']
        mins_secs = msecs_to_mins_and_secs(time_msecs)  # String
        delimiter = ":"
        if "." in mins_secs:
            delimiter = "."
        mins = int(mins_secs.split(delimiter)[0])
        secs = mins_secs.split(delimiter)[1]
        hours = int(mins / 60)
        remainder_mins = str(mins - hours * 60)
        if len(remainder_mins) == 1:
            remainder_mins = "0" + remainder_mins
        hours = str(hours)
        if len(hours) == 1:
            hours = '0' + hours
        ts = "\n"
        if fmt == "[mm.ss]":
            ts += '[' + str(mins) + '.' + secs + ']'
        if fmt == "[mm:ss]":
            ts += '[' + str(mins) + ':' + secs + ']'
        if fmt == "[hh.mm.ss]":
            ts += '[' + str(hours) + '.' + remainder_mins + '.' + secs + ']'
        if fmt == "[hh:mm:ss]":
            ts += '[' + str(hours) + ':' + remainder_mins + ':' + secs + ']'
        if fmt == "{hh:mm:ss}":
            ts += '{' + str(hours) + ':' + remainder_mins + ':' + secs + '}'
        if fmt == "#hh:mm:ss.sss#":
            msecs = "000"
            tms_str = str(time_msecs)
            if len(tms_str) > 2:
                msecs = tms_str[-3:]
            ts += '#' + str(hours) + ':' + remainder_mins + ':' + secs + '.' + msecs + '#'
        return "\n" + ts + " "

    def convert_to_flac(self):
        if len(self.filepath) < 5:
            return
        if self.filepath[-5:] in (".flac", ".FLAC"):
            self.flac_filepath = self.filepath
            return
        if self.filepath[-4:].lower() not in (".mp3", ".wav", ".m4a",  ".mp4", ".mov", ".ogg"):
            return
        audio = None
        if self.filepath[-4:].lower() == ".wav":
            audio = pydub.AudioSegment.from_wav(self.filepath)
        if self.filepath[-4:].lower() == ".mp3":
            audio = pydub.AudioSegment.from_mp3(self.filepath)
        if self.filepath[-4:].lower() == ".ogg":
            audio = pydub.AudioSegment.from_ogg(self.filepath)
        if self.filepath[-4:].lower() == ".mp4":
            audio = pydub.AudioSegment.from_file(self.filepath, "mp4")
        if self.filepath[-4:].lower() == ".mp4":
            audio = pydub.AudioSegment.from_file(self.filepath, "mov")
        if self.filepath[-4:].lower() == ".mp4":
            audio = pydub.AudioSegment.from_file(self.filepath, "m4a")
        if audio is not None:
            self.flac_filepath = self.filepath[:-4] + ".flac"
            audio.export(self.flac_filepath, format="flac")
