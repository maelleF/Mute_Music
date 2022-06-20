import os, sys, datetime, time
import threading

from .zmq_tools import *
import msgpack

import numpy as np
from scipy.spatial.distance import pdist
from psychopy import visual, core, data, logging, event
from .ellipse import Ellipse

from ..tasks.task_base import Task
from . import config

INSTRUCTION_DURATION = 5

CALIBRATE_HOTKEY = "c"
INSTRUCTION_DURATION = 5

MARKER_SIZE = 20 # this is the radius
#MARKER_FILL_COLOR = (0.8, 0, 0.5)
MARKER_DURATION_FRAMES = 90 #240 # 60 fps, 4s = 240; 60fps, 1.5s = 90 frames
'''
# 10-pt calibration
MARKER_POSITIONS = np.asarray(
    [
        (0.25, 0.5),
        (0, 0.5),
        (0.0, 1.0),
        (0.5, 1.0),
        (1.0, 1.0),
        (1.0, 0.5),
        (1.0, 0.0),
        (0.5, 0.0),
        (0.0, 0.0),
        (0.75, 0.5),
    ]
)
'''
# 9-pt calibration
MARKER_POSITIONS = np.asarray(
    [
        (0.5, 0.5),
        (0, 0.5),
        (0.0, 1.0),
        (0.5, 1.0),
        (1.0, 1.0),
        (1.0, 0.5),
        (1.0, 0.0),
        (0.5, 0.0),
        (0.0, 0.0),
    ]
)

# number of frames to eliminate at start and end of marker
CALIBRATION_LEAD_IN = 10 # 20
CALIBRATION_LEAD_OUT = 0 #20

# Pupil settings
PUPIL_REMOTE_PORT = 50123
CAPTURE_SETTINGS = {
    "frame_size": [640, 480],
    "frame_rate": 250,
    "exposure_time": 1500,
    #"exposure_time": 4000,
    "global_gain": 1,
    "gev_packet_size": 1400,
    "uid": "Aravis-Fake-GV01",  # for test purposes
    # "uid": "MRC Systems GmbH-GVRD-MRC HighSpeed-MR_CAM_HS_0014",
}


class EyetrackerCalibration(Task):
    def __init__(
        self,
        eyetracker,
        markers_order="random",
        #marker_fill_color=MARKER_FILL_COLOR,
        markers=MARKER_POSITIONS,
        use_eyetracking=True,
        validation=False,
        **kwargs,
    ):
        self.markers_order = markers_order
        self.markers = markers
        #self.marker_fill_color = marker_fill_color
        super().__init__(use_eyetracking=use_eyetracking, **kwargs)
        self.eyetracker = eyetracker
        self.validation = validation

    def _instructions(self, exp_win, ctl_win):
        if self.validation:
            instruction_text = """Eyetracker Validation.

    Once again, please fixate on the CENTER of the markers that appear on the screen."""
        else:
            instruction_text = """Eyetracker Calibration.

    You'll be asked to roll your eyes, then fixate on the CENTER of the markers that appear on the screen."""
        screen_text = visual.TextStim(
            exp_win,
            text=instruction_text,
            alignText="center",
            color="white",
            wrapWidth=config.WRAP_WIDTH,
        )

        for frameN in range(config.FRAME_RATE * INSTRUCTION_DURATION):
            screen_text.draw(exp_win)
            screen_text.draw(ctl_win)
            yield True

    def _setup(self, exp_win):
        self.use_fmri = False
        super()._setup(exp_win)
        self.fixation_dot = fixation_dot(exp_win, radius=MARKER_SIZE)


    def _pupil_cb(self, pupil):
        if pupil["timestamp"] > self.task_stop:
            self.eyetracker.unset_pupil_cb()
            return
        if pupil["timestamp"] > self.task_start:
            self._pupils_list.append(pupil)

    def _gaze_cb(self, gaze):
        if gaze["timestamp"] > self.task_stop:
            self.eyetracker.unset_gaze_cb()
            return
        if gaze["timestamp"] > self.task_start:
            self._gaze_list.append(gaze)

    def _fix_cb(self, fixation):
        if fixation["timestamp"] > self.task_stop:
            self.eyetracker.unset_fix_cb()
            return
        if fixation["timestamp"] > self.task_start:
            self._fix_list.append(fixation)

    def _run(self, exp_win, ctl_win):

        roll_eyes_text = "Please roll your eyes ~2-3 times in clockwise and counterclockwise directions"
        if self.validation:
            roll_eyes_text = "Get Ready" # no need to roll eyes again

        text_roll = visual.TextStim(
            exp_win,
            text=roll_eyes_text,
            alignText="center",
            color="white",
            wrapWidth=config.WRAP_WIDTH,
            )

        calibration_success = False
        while not calibration_success:
            while True:
                allKeys = event.getKeys([CALIBRATE_HOTKEY])
                start_calibration = False
                for key in allKeys:
                    if key == CALIBRATE_HOTKEY:
                        start_calibration = True
                if start_calibration:
                    break
                text_roll.draw(exp_win)
                yield False
            if self.validation:
                logging.info("validation started")
                print("validation started")
            else:
                logging.info("calibration started")
                print("calibration started")

            #window_size_frame = exp_win.size - MARKER_SIZE * 2
            window_size_frame = exp_win.size - 50 * 2 # 50 = previous MARKER_SIZE; hard-coded to maintain distance from screen edge regardless of target shape

            '''
            circle_marker = visual.Circle(
                exp_win,
                edges=64,
                units="pix",
                lineColor=None,
                #fillColor=self.marker_fill_color,
                autoLog=False,
            )
            '''

            markers_order = np.arange(len(self.markers))
            if self.markers_order == "random":
                markers_order = np.random.permutation(markers_order)

            self.all_refs_per_flip = []
            self._pupils_list = []
            self._gaze_list = []
            self._fix_list = []

            '''
            radius_anim = np.hstack(
                [
                    np.linspace(MARKER_SIZE, 0, MARKER_DURATION_FRAMES // 2),
                    np.linspace(0, MARKER_SIZE, MARKER_DURATION_FRAMES // 2),
                ]
            )
            '''

            self.task_start = time.monotonic()
            self.task_stop = np.inf
            self.eyetracker.set_pupil_cb(self._pupil_cb)
            self.eyetracker.set_gaze_cb(self._gaze_cb)
            self.eyetracker.set_fix_cb(self._fix_cb)

            while not len(self._pupils_list):  # wait until we get at least a pupil
                yield False

            if self.validation:
                exp_win.logOnFlip(
                    level=logging.EXP,
                    msg="eyetracker_validation: starting at %f" % time.time(),
                )
            else:
                exp_win.logOnFlip(
                    level=logging.EXP,
                    msg="eyetracker_calibration: starting at %f" % time.time(),
                )
            for site_id in markers_order:
                marker_pos = self.markers[site_id]
                pos = (marker_pos - 0.5) * window_size_frame # remove 0.5 since 0, 0 is the middle in psychopy
                #circle_marker.pos = pos
                for stim in self.fixation_dot:
                    stim.pos = pos
                if self.validation:
                    exp_win.logOnFlip(
                        level=logging.EXP,
                        msg="validate_position,%d,%d,%d,%d"
                        % (marker_pos[0], marker_pos[1], pos[0], pos[1]),
                    )
                else:
                    exp_win.logOnFlip(
                        level=logging.EXP,
                        msg="calibrate_position,%d,%d,%d,%d"
                        % (marker_pos[0], marker_pos[1], pos[0], pos[1]),
                    )
                exp_win.callOnFlip(
                    self._log_event, {"marker_x": pos[0], "marker_y": pos[1]}
                )
                #for f, r in enumerate(radius_anim):
                for f in range(MARKER_DURATION_FRAMES):
                    #circle_marker.radius = r
                    #circle_marker.draw(exp_win)
                    #circle_marker.draw(ctl_win)
                    for stim in self.fixation_dot:
                        stim.draw(exp_win)
                        stim.draw(ctl_win)

                    if (
                        f > CALIBRATION_LEAD_IN
                        #and f < len(radius_anim) - CALIBRATION_LEAD_OUT
                        and f < MARKER_DURATION_FRAMES - CALIBRATION_LEAD_OUT
                    ):
                        screen_pos = pos + exp_win.size / 2
                        norm_pos = screen_pos / exp_win.size
                        ref = {
                            "norm_pos": norm_pos.tolist(),
                            "screen_pos": screen_pos.tolist(),
                            "timestamp": time.monotonic(),  # =pupil frame timestamp on same computer
                        }
                        self.all_refs_per_flip.append(ref)  # accumulate all refs
                    yield True
            yield True
            self.task_stop = time.monotonic()
            if self.validation:
                logging.info(
                    f"validating on {len(self._pupils_list)} pupils and {len(self.all_refs_per_flip)} markers"
                )
            else:
                logging.info(
                    f"calibrating on {len(self._pupils_list)} pupils and {len(self.all_refs_per_flip)} markers"
                )
            if self.validation:
                #TODO: debug validate function below...
                print('Ǹumber of received fixations: ', str(len(self._fix_list)))
                self.eyetracker.validate(self._fix_list, self.all_refs_per_flip)
                calibration_success = True
            else:
                self.eyetracker.calibrate(self._pupils_list, self.all_refs_per_flip)
                while True:
                    notes = getattr(self.eyetracker, '_last_calibration_notification',None)
                    if notes:
                        calibration_success = notes['topic'].startswith("notify.calibration.successful")
                        if not calibration_success:
                            print('#### CALIBRATION FAILED: restart with <c> ####')
                        break


    def stop(self, exp_win, ctl_win):
        self.eyetracker.unset_pupil_cb()
        self.eyetracker.unset_gaze_cb()
        self.eyetracker.unset_fix_cb()
        yield

    def _save(self):
        if hasattr(self, "_pupils_list"):
            if self.validation:
                fname = self._generate_unique_filename("valid-data", "npz")
            else:
                fname = self._generate_unique_filename("calib-data", "npz")
            np.savez(fname, pupils=self._pupils_list,
                            gaze=self._gaze_list,
                            fixations=self._fix_list,
                            markers=self.all_refs_per_flip)
            #np.savez(fname, pupils=self._pupils_list, markers=self.all_refs_per_flip)

class EyetrackerSetup(Task):
    def __init__(
        self,
        eyetracker,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.eyetracker = eyetracker

    def _run(self, exp_win, ctl_win):

        con_text_str = "Trying to establish connection to the eyetracker %s"

        con_text = visual.TextStim(
            exp_win,
            text=con_text_str % ' ...',
            alignText="center",
            color="white",
            wrapWidth=config.WRAP_WIDTH,
            )
        con_text.draw(exp_win)
        yield True

        while True:
            notif = self.eyetracker._aravis_notification
            print(notif)
            if (
                notif and
                notif["subject"] == "aravis.start_capture.successful" and
                notif["target"] == "eye0" and
                notif["name"] == "Aravis_Source"):
                break

            self.eyetracker.start_source()
            con_text.text = con_text_str % 'failed, retrying'
            con_text.draw(exp_win)
            yield True
            time.sleep(3)



from subprocess import Popen

from contextlib import contextmanager


@contextmanager
def nonblocking(lock):
    locked = lock.acquire(False)
    try:
        yield locked
    finally:
        if locked:
            lock.release()


class EyeTrackerClient(threading.Thread):

    EYE = "eye0"

    def __init__(self, output_path, output_fname_base, profile=False, debug=False):
        super(EyeTrackerClient, self).__init__()
        self.stoprequest = threading.Event()
        self.lock = threading.Lock()

        self.pupil = None
        self.gaze = None
        self.fixation = None
        self.unset_pupil_cb()
        self.unset_gaze_cb()
        self.unset_fix_cb()

        self.output_path = output_path
        self.output_fname_base = output_fname_base
        self.record_dir = os.path.join(
            self.output_path, self.output_fname_base + ".pupil"
        )
        os.makedirs(self.record_dir, exist_ok=True)

        dev_opts = []
        if debug:
            dev_opts.append("--debug")
        if profile:
            dev_opts.append("--profile")

        pupil_logfile = open(os.path.join(self.record_dir, "pupil.log"), "wb")
        pupil_env = os.environ.copy()
        pupil_env.update({'ARV_DEBUG':'all:2'})

        self._pupil_process = Popen(
            [
                "python3",
                os.path.join(os.environ["PUPIL_PATH"], "pupil_src", "main.py"),
                "capture",
                "--port",
                str(PUPIL_REMOTE_PORT),
            ]
            + dev_opts,
            env=pupil_env,
            stdout=pupil_logfile,
            stderr=pupil_logfile,
        )

        self._ctx = zmq.Context()
        self._req_socket = self._ctx.socket(zmq.REQ)
        self._req_socket.connect(f"tcp://localhost:{PUPIL_REMOTE_PORT}")

        # stop eye1 if started: monocular eyetracking in the MRI
        notif = self.send_recv_notification(
            {"subject": "eye_process.should_stop.1", "eye_id": 1, "args": {}}
        )

        # start eye0 if not started yet (from pupil saved config)
        notif = self.send_recv_notification(
            {"subject": "eye_process.should_start.0", "eye_id": 0, "args": {}}
        )

        # wait for eye process to start before starting plugins
        time.sleep(1)

        # quit existing recorder plugin
        self.send_recv_notification(
            {
                "subject": "stop_plugin",
                "name": "Recorder",
            }
        )
        # restart recorder plugin with custom output settings
        self.send_recv_notification(
            {
                "subject": "start_plugin",
                "name": "Recorder",
                "args": {
                    "rec_root_dir": self.record_dir,
                    "session_name": self.output_fname_base + ".pupil",
                    "raw_jpeg": False,
                    "record_eye": True,
                },
            }
        )

        # restart 2d detector plugin with custom output settings
        self.send_recv_notification(
            {
                "subject": "start_eye_plugin",
                "name": "Detector2DPlugin",
                "target": self.EYE,
                "args": {
                    "properties": {
                        "intensity_range": 4,
                    }
                },
            }
        )

        # stop a bunch of eye plugins for performance
        for plugin in ["NDSI_Manager", "Pye3DPlugin"]:
            self.send_recv_notification(
                {
                    "subject": "stop_eye_plugin",
                    "target": self.EYE,
                    "name": plugin,
                }
            )
        self.start_source()

    def start_source(self):
        self.send_recv_notification(
            {
                "subject": "start_eye_plugin",
                "name": "Aravis_Source",
                "target": self.EYE,
                "args": CAPTURE_SETTINGS,
            }
        )

    def send_recv_notification(self, n):
        # REQ REP requires lock step communication with multipart msg (topic,msgpack_encoded dict)
        self._req_socket.send_multipart(
            (bytes("notify.%s" % n["subject"], "utf-8"), msgpack.dumps(n))
        )
        return self._req_socket.recv()

    def get_pupil_timestamp(self):
        self._req_socket.send("t")  # see Pupil Remote Plugin for details
        return float(self._req_socket.recv())

    def start_recording(self, recording_name):
        logging.info("starting eyetracking recording")
        return self.send_recv_notification(
            {"subject": "recording.should_start", "session_name": recording_name}
        )

    def stop_recording(self):
        logging.info("stopping eyetracking recording")
        return self.send_recv_notification({"subject": "recording.should_stop"})

    def join(self, timeout=None):
        self.stoprequest.set()
        # stop recording
        self.send_recv_notification(
            {
                "subject": "recording.should_stop",
            }
        )
        # stop world and children process
        self.send_recv_notification({"subject": "world_process.should_stop"})
        self.send_recv_notification({"subject": "launcher_process.should_stop"})
        self._pupil_process.wait(timeout)
        self._pupil_process.terminate()
        time.sleep(1 / 60.0)
        super(EyeTrackerClient, self).join(timeout)

    def run(self):

        self._aravis_notification = None
        self._req_socket.send_string("SUB_PORT")
        ipc_sub_port = int(self._req_socket.recv())
        logging.info(f"ipc_sub_port: {ipc_sub_port}")
        self.pupil_monitor = Msg_Receiver(
            self._ctx, f"tcp://localhost:{ipc_sub_port}",
            topics=("gaze", "pupil", "fixations", "notify.calibration.successful", "notify.calibration.failed", "notify.aravis")
        )
        while not self.stoprequest.isSet():
            msg = self.pupil_monitor.recv()
            if not msg is None:
                topic, tmp = msg
                with self.lock:
                    if topic.startswith("pupil"):
                        self.pupil = tmp
                        if self._pupil_cb:
                            self._pupil_cb(tmp)
                    elif topic.startswith("gaze"):
                        self.gaze = tmp
                        if self._gaze_cb:
                            self._gaze_cb(tmp)
                    elif topic.startswith("fixations"):
                        self.fixation = tmp
                        if self._fix_cb:
                            self._fix_cb(tmp)
                    elif topic.startswith("notify.calibration"):
                        self._last_calibration_notification = tmp
                    elif topic.startswith("notify.aravis.start_capture"):
                        self._aravis_notification = tmp
            time.sleep(1e-3)
        logging.info("eyetracker listener: stopping")

    def set_pupil_cb(self, pupil_cb):
        self._pupil_cb = pupil_cb

    def set_gaze_cb(self, gaze_cb):
        self._gaze_cb = gaze_cb

    def set_fix_cb(self, fix_cb):
        self._fix_cb = fix_cb

    def unset_pupil_cb(self):
        self._pupil_cb = None

    def unset_gaze_cb(self):
        self._gaze_cb = None

    def unset_fix_cb(self):
        self._fix_cb = None

    def get_pupil(self):
        with nonblocking(self.lock) as locked:
            if locked:
                return self.pupil

    def get_gaze(self):
        with nonblocking(self.lock) as locked:
            if locked:
                return self.gaze


    def get_marker_dictionary(self, ref_list):
        position_list = []
        markers_dict = {}
        count = 0

        for i in range(len(ref_list)):
            m = ref_list[i]
            if not (m['norm_pos']) in position_list:
                markers_dict[count] = {
                    'norm_pos': m['norm_pos'],
                    'screen_pos': m['screen_pos'],
                    'onset': m['timestamp'],
                    'offset': -1.0,
                }
                count += 1
                position_list.append(m['norm_pos'])
            elif m['timestamp'] > markers_dict[count-1]['offset']:
                markers_dict[count-1]['offset'] = m['timestamp']

        return markers_dict


    def assign_fix_to_markers(self, fixation_list, markers_dict):
        '''
        Assign fixations to markers based on their onset.
        A fixation is assigned to a marker if its ONSET overlaps with the time the marker is on the screen
        '''
        i = 0
        #print(markers_dict[0]['onset'], fixation_list[0]['timestamp'])
        for count in range(len(markers_dict.keys())):
            marker = markers_dict[count]
            fix_dict = {}

            while i < len(fixation_list) and fixation_list[i]['timestamp'] < marker['onset']:
                i += 1

            while i < len(fixation_list) and fixation_list[i]['timestamp'] < marker['offset']:
                fix = fixation_list[i]
                if fix['id'] not in fix_dict:
                    fix_dict[fix['id']] = {
                                        'timestamps': [fix['timestamp']],
                                        'norm_pos': [fix['norm_pos']],
                                        'durations': [fix['duration']],
                                        'dispersions': [fix['dispersion']],
                    }
                else:
                    fix_dict[fix['id']]['timestamps'].append(fix['timestamp'])
                    fix_dict[fix['id']]['norm_pos'].append(fix['norm_pos'])
                    fix_dict[fix['id']]['durations'].append(fix['duration'])
                    fix_dict[fix['id']]['dispersions'].append(fix['dispersion'])
                i += 1

            markers_dict[count]['fix_dict'] = fix_dict

        return markers_dict


    def fix_to_marker_distances(self, markers_dict):
        '''
        estimated eye-to-screen distance in pixels
        based on screen dim in pixels ((1280, 1024)) and screen deg of visual angle (17.5, 14)
        '''
        dist_in_pix = 4164 # in pixels

        print('Distance between gaze and target in degrees of visual angle')
        print('Good < 0.5 deg ; Fair = [0.5, 1.5[ deg ; Poor >= 1.5 deg')

        for count in range(len(markers_dict.keys())):
            m = markers_dict[count]
            print('Marker ' + str(count) + ', Normalized position: ' +  str(m['norm_pos']))

            # transform marker's normalized position into dim = (3,) vector in pixel space
            m_vecpos = np.concatenate(((np.array(m['norm_pos']) - 0.5)*(1280, 1024), np.array([dist_in_pix])), axis=0)

            for key in m['fix_dict'].keys():
                fix = (np.array(m['fix_dict'][key]['norm_pos']) - 0.5)*(1280, 1024)
                fix_vecpos = np.concatenate((fix, np.repeat(dist_in_pix, len(fix)).reshape((-1, 1))), axis=1)

                distances = []
                for fix_vec in fix_vecpos:
                    vectors = np.stack((m_vecpos, fix_vec), axis=0)
                    distance = np.rad2deg(np.arccos(1.0 - pdist(vectors, metric='cosine')))

                    distances.append(distance[0])

                distances = np.array(distances)
                markers_dict[count]['fix_dict'][key]['distances'] = distances

                num_fix = len(distances)
                good = np.sum(distances < 0.5) / num_fix
                fair = np.sum((distances >= 0.5)*(distances < 1.5)) / num_fix
                poor = np.sum(distances >= 1.5) / num_fix

                print('Total fixations:' + str(num_fix) + ' , Good:' + str(good) + ' , Fair:' + str(fair) + ' , Poor:' + str(poor))

        return markers_dict


    def interleave_calibration(self, tasks):
        calibration_index=0
        for task in tasks:
            calibration_index+=1
            if task.use_eyetracking:
                yield EyetrackerCalibration(
                    self,
                    name=f"eyeTrackercalibration-{calibration_index}"
                    )
                yield EyetrackerCalibration(
                    self,
                    name=f"eyeTrackercalib-validate-{calibration_index}",
                    validation=True
                    )
            yield task

    def calibrate(self, pupil_list, ref_list):
        if len(pupil_list) < 100:
            logging.error("Calibration: not enough pupil captured for calibration")
            # return

        # TODO: check num of quality pupils per fixation points, set quality threshold...

        calib_data = {"ref_list": ref_list, "pupil_list": pupil_list}

        logging.info("sending calibration data to pupil")
        calib_res = self.send_recv_notification(
            {
                "subject": "start_plugin",
                "name": "Gazer2D",
                "args": {"calib_data": calib_data},
                "raise_calibration_error": False,
            }
        )

    def validate(self, fixation_list, ref_list):

        markers_dict = self.get_marker_dictionary(ref_list)
        markers_dict = self.assign_fix_to_markers(fixation_list, markers_dict)
        markers_dict = self.fix_to_marker_distances(markers_dict)
        # TODO : export validation distances?


class GazeDrawer:
    def __init__(self, win):

        self.win = win
        self._gazepoint_stim = visual.Circle(
            self.win,
            radius=30,
            units="pix",
            lineColor=(1, 0, 0),
            fillColor=None,
            lineWidth=2,
            autoLog=False,
        )

    def draw_gazepoint(self, gaze):
        pos = gaze["norm_pos"]
        self._gazepoint_stim.pos = (
            int(pos[0] / 2 * self.win.size[0]),
            int(pos[1] / 2 * self.win.size[1]),
        )
        # self._gazepoint_stim.radius = self.pupils['diameter']/2
        # print(self._gazepoint_stim.pos, self._gazepoint_stim.radius)
        self._gazepoint_stim.draw(self.win)


def read_pl_data(fname):
    with open(fname, "rb") as fh:
        for data in msgpack.Unpacker(fh, raw=False, use_list=False):
            yield (data)


def fixation_dot(win, **kwargs):
    #radius = kwargs.pop('radius', 30)
    radius = kwargs.pop('radius', 20)
    kwargs = {
        'lineColor': (1,-.5,-.5),
        'fillColor': (1,1,1),
        'units': 'pix',
        **kwargs
    }
    circle = visual.Circle(win, lineWidth=radius*.4, **kwargs, radius=radius)
    dot = visual.Circle(win, units=kwargs["units"], radius=radius*.25, lineWidth=0, fillColor=(-1,-1,-1))
    #dot = visual.Circle(win, units=kwargs["units"], radius=radius*.2, lineWidth=0, fillColor=(-1,-1,-1))
    return (circle, dot)
