/**
 * Project issue instances with their base commits and project directory mappings.
 * Each entry maps an issue to the commit at which it was reported,
 * so the extension can reconstruct the exact codebase state.
 */

export interface InstanceInfo {
  instanceId: string;
  baseCommit: string;
  projectDir: string; // directory name under projects/
}

export const MODEL_NAME = "deepseek-chat";

export const INSTANCES: InstanceInfo[] = [
  // sqlfluff
  { instanceId: "sqlfluff__sqlfluff-1625", baseCommit: "14e1a23a3166b9a645a16de96f694c77a5d4abb7", projectDir: "sqlfluff" },
  { instanceId: "sqlfluff__sqlfluff-2419", baseCommit: "f1dba0e1dd764ae72d67c3d5e1471cf14d3db030", projectDir: "sqlfluff" },
  { instanceId: "sqlfluff__sqlfluff-1733", baseCommit: "a1579a16b1d8913d9d7c7d12add374a290bcc78c", projectDir: "sqlfluff" },
  { instanceId: "sqlfluff__sqlfluff-1517", baseCommit: "304a197829f98e7425a46d872ada73176137e5ae", projectDir: "sqlfluff" },
  { instanceId: "sqlfluff__sqlfluff-1763", baseCommit: "a10057635e5b2559293a676486f0b730981f037a", projectDir: "sqlfluff" },

  // marshmallow
  { instanceId: "marshmallow-code__marshmallow-1359", baseCommit: "b40a0f4e33823e6d0f341f7e8684e359a99060d1", projectDir: "marshmallow" },
  { instanceId: "marshmallow-code__marshmallow-1343", baseCommit: "2be2d83a1a9a6d3d9b85804f3ab545cecc409bb0", projectDir: "marshmallow" },

  // pvlib-python
  { instanceId: "pvlib__pvlib-python-1707", baseCommit: "40e9e978c170bdde4eeee1547729417665dbc34c", projectDir: "pvlib-python" },
  { instanceId: "pvlib__pvlib-python-1072", baseCommit: "04a523fafbd61bc2e49420963b84ed8e2bd1b3cf", projectDir: "pvlib-python" },
  { instanceId: "pvlib__pvlib-python-1606", baseCommit: "c78b50f4337ecbe536a961336ca91a1176efc0e8", projectDir: "pvlib-python" },
  { instanceId: "pvlib__pvlib-python-1854", baseCommit: "27a3a07ebc84b11014d3753e4923902adf9a38c0", projectDir: "pvlib-python" },
  { instanceId: "pvlib__pvlib-python-1154", baseCommit: "0b8f24c265d76320067a5ee908a57d475cd1bb24", projectDir: "pvlib-python" },

  // astroid
  { instanceId: "pylint-dev__astroid-1978", baseCommit: "0c9ab0fe56703fa83c73e514a1020d398d23fa7f", projectDir: "astroid" },
  { instanceId: "pylint-dev__astroid-1333", baseCommit: "d2a5b3c7b1e203fec3c7ca73c30eb1785d3d4d0a", projectDir: "astroid" },
  { instanceId: "pylint-dev__astroid-1196", baseCommit: "39c2a9805970ca57093d32bbaf0e6a63e05041d8", projectDir: "astroid" },
  { instanceId: "pylint-dev__astroid-1866", baseCommit: "6cf238d089cf4b6753c94cfc089b4a47487711e5", projectDir: "astroid" },
  { instanceId: "pylint-dev__astroid-1268", baseCommit: "ce5cbce5ba11cdc2f8139ade66feea1e181a7944", projectDir: "astroid" },

  // pyvista
  { instanceId: "pyvista__pyvista-4315", baseCommit: "db6ee8dd4a747b8864caae36c5d05883976a3ae5", projectDir: "pyvista" },

  // pydicom
  { instanceId: "pydicom__pydicom-1694", baseCommit: "f8cf45b6c121e5a4bf4a43f71aba3bc64af3db9c", projectDir: "pydicom" },
  { instanceId: "pydicom__pydicom-1413", baseCommit: "f909c76e31f759246cec3708dadd173c5d6e84b1", projectDir: "pydicom" },
  { instanceId: "pydicom__pydicom-901",  baseCommit: "3746878d8edf1cbda6fbcf35eec69f9ba79301ca", projectDir: "pydicom" },
  { instanceId: "pydicom__pydicom-1139", baseCommit: "b9fb05c177b685bf683f7f57b2d57374eb7d882d", projectDir: "pydicom" },
  { instanceId: "pydicom__pydicom-1256", baseCommit: "49a3da4a3d9c24d7e8427a25048a1c7d5c4f7724", projectDir: "pydicom" },
];

/** Absolute path to the projects directory. */
export const PROJECTS_ROOT = "/home/arshia2562/Documents/Uni/Term-8/FP/projects";

/** Absolute path to the results JSONL file. */
export const RESULTS_PATH = "/home/arshia2562/Documents/Uni/Term-8/FP/results/swe_bench_lite_results.jsonl";
