"use strict";
/* The scorecard lives in the shared core (RotCore.scorecard) so both editions read the match the same way; this alias keeps
   the Hub's older references working. */
(function(root){ const R=root.RotCore||(typeof require==="function"?require("../core/rot_core.js"):null); if(root.CCH) root.CCH.Scorecard=R.scorecard; else root.CCH={Scorecard:R.scorecard}; if(typeof module!=="undefined"&&module.exports) module.exports=R.scorecard; })(typeof globalThis!=="undefined"?globalThis:this);
