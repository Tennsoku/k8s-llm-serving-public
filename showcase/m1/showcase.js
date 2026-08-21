"use strict";

import {startRunApp} from "../shared/run-app.js";

startRunApp({
  entryContract: Object.freeze({
    parseEntry(raw, prefix, {assert, parseSingle}) {
      assert(raw.summary_set == null, prefix + ".summary_set 不受 M1 contract 支持。");
      return parseSingle();
    }
  })
});
