"use strict";

import {startRunApp} from "../shared/run-app.js";

startRunApp({
  entryContract: Object.freeze({
    parseEntry(raw, prefix, {assert, parseSingle, parseSummarySet}) {
      const hasSet = raw.summary_set != null;
      const hasSingle = raw.expected_run_id != null || raw.summary_path != null;
      assert(hasSet !== hasSingle, prefix + " 必须且只能声明 single summary 或 summary_set。");
      return hasSet ? parseSummarySet() : parseSingle();
    }
  })
});
