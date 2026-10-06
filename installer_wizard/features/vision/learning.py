import logging
import os
import time

import numpy as np

import selection

log = logging.getLogger("atena.vision")
AUTO_ENROLL = os.environ.get("ATENA_AUTO_ENROLL", "1") != "0"
AUTO_MIN_SECONDS = 2.5
AUTO_MIN_RATIO = 0.09
AUTO_SAMPLES = 8
MERGE_THRESHOLD = 0.30
LEARN_UNTIL = 25
LEARN_EVERY = 1.5
REFINE_EVERY = 60.0
MERGE_CENTROID = float(os.environ.get("ATENA_FACE_MERGE_CENTROID", "0.45"))
REFINE = os.environ.get("ATENA_FACE_AUTOIMPROVE", "1") != "0"


def learn(vision, track, frame, feature) -> None:
    if not AUTO_ENROLL or vision.enroll_request is not None or track.echo_of or track.ambiguous:
        return
    if selection.liveness_mode() != "off" and vision.fusion.active and track.live_state != "live":
        return
    now = time.time()
    slug, name, score = track.identity()
    ratio = track.box[2] / (vision.size[0] or 640)
    ir = [track.ir_feature] if track.ir_feature is not None else None
    if slug:
        person = vision.gallery.people.get(slug, {})
        young = person.get("samples", 40) < LEARN_UNTIL
        wait = LEARN_EVERY if young else REFINE_EVERY
        if (young or REFINE) and score > 0.5 and track.facing and now - track.last_learn > wait \
                and vision.gallery.may_learn(slug, feature, track.ir_feature):
            track.last_learn = now
            vision.gallery.add_samples(slug, [feature], ir)
        return
    if ratio < AUTO_MIN_RATIO or any(t.identity()[0] for t in vision.tracks):
        return
    track.samples.append(feature)
    if track.ir_feature is not None:
        track.ir_samples.append(track.ir_feature)
    if now - track.first_seen < AUTO_MIN_SECONDS or len(track.samples) < AUTO_SAMPLES:
        return
    mean = np.mean([s / np.linalg.norm(s) for s in track.samples], axis=0)
    near_slug, near_score = vision.gallery.closest(mean)
    centroid_ok = near_slug is not None and float(vision.gallery.people[near_slug]["centroid"] @ (mean / np.linalg.norm(mean))) >= MERGE_CENTROID
    if near_slug and near_score >= MERGE_THRESHOLD and centroid_ok:
        vision.gallery.add_samples(near_slug, track.samples, track.ir_samples or None)
        log.info("Campioni aggiunti a %s (somiglianza %.2f)", near_slug, near_score)
    else:
        guest = vision.gallery.next_guest_name()
        person = vision.gallery.save(guest, track.samples, vision._crop(frame, track.box), auto=True,
                                   slug=f"ospite-{int(now)}", ir=track.ir_samples or None)
        log.info("Nuova persona registrata automaticamente: %s", person["name"])
    track.samples, track.ir_samples = [], []
    track.votes.clear()

