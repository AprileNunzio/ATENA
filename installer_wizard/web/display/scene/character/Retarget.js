(function (J) {
  "use strict";
  const { THREE } = J;
  const C = (J.Char = J.Char || {});

  function relative(root, obj) {
    root.updateMatrixWorld(true);
    return new THREE.Matrix4().copy(root.matrixWorld).invert().multiply(obj.matrixWorld);
  }

  function rotation(m) {
    const p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
    m.decompose(p, q, s);
    return q;
  }

  function hipsHeight(root, map) {
    const hips = map.hips;
    return hips ? Math.max(1e-6, new THREE.Vector3().setFromMatrixPosition(relative(root, hips)).y) : 1;
  }

  function rotationTrack(track, src, dst, name) {
    const Gs = rotation(relative(src.root, src.bone)), Gsp = rotation(relative(src.root, src.bone.parent));
    const Gt = rotation(relative(dst.root, dst.bone)), Gtp = rotation(relative(dst.root, dst.bone.parent));
    const pre = Gtp.clone().invert().multiply(Gsp), post = Gs.clone().invert().multiply(Gt);
    const v = new Float32Array(track.values.length), q = new THREE.Quaternion();
    for (let i = 0; i < v.length; i += 4) {
      q.fromArray(track.values, i);
      q.premultiply(pre).multiply(post).normalize().toArray(v, i);
    }
    return new THREE.QuaternionKeyframeTrack(`${name}.quaternion`, Float32Array.from(track.times), v);
  }

  function positionTrack(track, src, dst, name, ratio) {
    const Ms = relative(src.root, src.bone.parent), Mt = relative(dst.root, dst.bone.parent), MtInv = Mt.clone().invert();
    const s0 = src.bone.position.clone().applyMatrix4(Ms), t0 = dst.bone.position.clone().applyMatrix4(Mt);
    const v = new Float32Array(track.values.length), p = new THREE.Vector3();
    for (let i = 0; i < v.length; i += 3) {
      p.fromArray(track.values, i).applyMatrix4(Ms).sub(s0).multiplyScalar(ratio).add(t0).applyMatrix4(MtInv);
      p.toArray(v, i);
    }
    return new THREE.VectorKeyframeTrack(`${name}.position`, Float32Array.from(track.times), v);
  }

  function retarget(clip, srcRoot, dstRoot, rename) {
    const srcMap = C.byCanon(srcRoot), dstMap = C.byCanon(dstRoot);
    const ratio = hipsHeight(dstRoot, dstMap) / hipsHeight(srcRoot, srcMap);
    const tracks = [];
    for (const track of clip.tracks) {
      const parsed = THREE.PropertyBinding.parseTrackName(track.name), key = C.canon(parsed.nodeName);
      const sb = srcMap[key], db = dstMap[key];
      if (!sb || !db || !sb.parent || !db.parent) continue;
      const src = { root: srcRoot, bone: sb }, dst = { root: dstRoot, bone: db };
      if (parsed.propertyName === "quaternion") tracks.push(rotationTrack(track, src, dst, db.name));
      else if (parsed.propertyName === "position" && key === "hips") tracks.push(positionTrack(track, src, dst, db.name, ratio));
    }
    return tracks.length ? new THREE.AnimationClip(rename || clip.name, clip.duration, tracks) : null;
  }

  function native(clip, root) {
    const map = C.byCanon(root), tracks = [];
    for (const track of clip.tracks) {
      const parsed = THREE.PropertyBinding.parseTrackName(track.name), key = C.canon(parsed.nodeName);
      if (parsed.propertyName === "scale" || (parsed.propertyName === "position" && key !== "hips")) continue;
      if (map[key] || parsed.nodeName === root.name) tracks.push(track);
    }
    return new THREE.AnimationClip(clip.name, clip.duration, tracks);
  }

  C.retarget = retarget;
  C.nativeClip = native;
})(window.Atena3D);
