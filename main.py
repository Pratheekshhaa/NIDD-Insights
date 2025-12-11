from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
import os
from collections import defaultdict, deque
import shutil
import re
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from io import BytesIO
import base64

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMP_FOLDER'] = 'temp_uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)

# ----------------- Globals -----------------
# parameters_list now contains ABBREVIATIONS (what shows in dropdown)
parameters_list = []  # used by dropdown: ONLY abbreviations
parameter_relations = {}  # key: ABBREVIATION (col D), value: list of related ABBREVIATIONS (from col P)
uml_data = defaultdict(lambda: {
    "attributes": [],
    "relationships": set(),
    "multiplicities": {}
})

# NEW: mappings for Option A
abbrev_to_param = {}   # abbrev -> Full Parameter Name (col C)
param_to_abbrev = {}   # Full Parameter Name -> abbrev (col D)

# Maximum attributes to show before "View More"
MAX_VISIBLE_ATTRIBUTES = 10


# ----------------- Helpers -----------------
def sanitize_for_mermaid(text):
    if not text:
        return ""
    text = str(text).strip()
    text = text.replace('"', "'")
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = ' '.join(text.split())
    return text


def create_safe_node_id(class_name):
    safe_id = re.sub(r'[^a-zA-Z0-9]', '_', class_name)
    safe_id = re.sub(r'\+', '', safe_id)
    safe_id = safe_id.strip('_')
    return safe_id if safe_id else 'node'


def parse_related_cell(cell_value):
    """
    Parse a cell from Column P and return a list of abbreviations.
    - Items separated by ';'
    - Each item can be like 'ABBR::public' -> strip '::...' suffix
    """
    out = []
    if pd.isna(cell_value):
        return out
    s = str(cell_value).strip()
    if not s:
        return out
    parts = [p.strip() for p in s.split(';') if p.strip()]
    for part in parts:
        # remove ::anything suffix (e.g. ::public)
        cleaned = re.sub(r'\s*::\s*.*$', '', part, flags=re.IGNORECASE).strip()
        if cleaned:
            out.append(cleaned)
    return out


# --------- Parameter Relation Finder ---------
def detect_header(df, search_columns):
    """Auto-detect header row by looking for keywords"""
    for i in range(min(10, len(df))):
        row = df.iloc[i].astype(str).str.lower()
        # if any search keyword appears anywhere in that row
        if any(keyword.lower() in " ".join(row.values) for keyword in search_columns):
            return i
    return 0


def load_excel_data(file_paths):
    """
    Load parameter data from multiple Excel files.
    - Column C (index 2) -> Full Parameter Name
    - Column D (index 3) -> Abbreviation (used everywhere for relations)
    - Column P (index 15) -> Related abbreviations list (semicolon-separated, may have ::public)
    - parameters_list will contain abbreviations
    - parameter_relations: abbrev -> list of related abbrevs
    - also populate abbrev_to_param and param_to_abbrev
    """
    global parameters_list, parameter_relations, abbrev_to_param, param_to_abbrev
    parameters_list = []
    parameter_relations = {}
    abbrev_to_param = {}
    param_to_abbrev = {}

    try:
        for file_path in file_paths:
            # read all sheets, no header so we can detect header row manually
            try:
                df_sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl', header=None)
            except Exception:
                # fallback to default read if any issue
                df_sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')

            for sheet_name, df in df_sheets.items():
                # skip tiny sheets
                if df.shape[1] < 16:
                    continue

                # detect header row heuristically
                header_row = detect_header(df, search_columns=["Parameter", "Parameter Name", "Abbreviation", "Relation", "Related"])
                df.columns = df.iloc[header_row]
                df = df.iloc[header_row + 1:].reset_index(drop=True)

                # Column indexes according to your request:
                # C -> index 2, D -> index 3, P -> index 15
                try:
                    col_full = df.columns[2]   # Column C (Full Parameter Name)
                    col_abbr = df.columns[3]   # Column D (Abbreviation)
                    col_rel = df.columns[15]   # Column P (Related list)
                except Exception:
                    # If headers messed up, skip this sheet
                    continue

                df_clean = df.dropna(subset=[col_full], how='all')

                for _, row in df_clean.iterrows():
                    full_name = str(row[col_full]).strip() if pd.notna(row[col_full]) else ""
                    abbrev = str(row[col_abbr]).strip() if pd.notna(row[col_abbr]) else ""
                    related_cell = row[col_rel] if col_rel in df.columns else ""

                    # If abbreviation is empty, fallback to a cleaned form of full_name
                    if not abbrev or abbrev.lower() in ['nan', 'none']:
                        abbrev = re.sub(r'\s+', '_', full_name).strip() if full_name else ""

                    if not full_name:
                        # skip rows without a full name
                        continue

                    # register mappings
                    if abbrev:
                        abbrev_to_param[abbrev] = full_name
                        # keep first abbreviation if multiple map to same full name; prefer abbrev
                        if full_name not in param_to_abbrev:
                            param_to_abbrev[full_name] = abbrev
                    else:
                        # no abbrev: still add mapping keyed by generated abbrev
                        continue

                    # add to dropdown list (unique)
                    if abbrev and abbrev not in parameters_list:
                        parameters_list.append(abbrev)

                    # parse relations from Column P (convert to abbrev list)
                    rels = parse_related_cell(related_cell)
                    # sanitize and dedupe
                    rels = [r for r in [x.strip() for x in rels] if r and r.lower() not in ['nan', 'none', '']]
                    if rels:
                        existing = parameter_relations.get(abbrev, [])
                        combined = list(set(existing + rels))
                        parameter_relations[abbrev] = combined
                    else:
                        # ensure the key exists with empty list rather than a string
                        if abbrev not in parameter_relations:
                            parameter_relations[abbrev] = []

        # sort dropdown alphabetically and keep unique
        parameters_list = sorted(list(set(parameters_list)))

    except Exception as e:
        print(f"Failed to load Excel: {e}")


# --------- UML Diagram Generator (UNCHANGED) ---------
def load_uml_data(file_paths):
    """Load UML data from multiple Excel files"""
    global uml_data
    uml_data.clear()
    all_classes = set()

    try:
        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue

            df = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')

            for sheet in df:
                data = df[sheet]
                if data.shape[1] < 31:
                    continue

                data = data.rename(columns={
                    data.columns[1]: "MOC_Name",
                    data.columns[2]: "Parameter_Name",
                    data.columns[3]: "Abbreviation",
                    data.columns[4]: "Data_Type",
                    data.columns[5]: "Parent_Parameter",
                    data.columns[25]: "Required_On_Creation",
                    data.columns[27]: "Required_On_Creation_Col_AB",
                    data.columns[28]: "Modification",
                    data.columns[29]: "MinOccurs",
                    data.columns[30]: "MaxOccurs"
                })

                data = data.dropna(subset=["MOC_Name", "Parameter_Name"], how='all')

                for _, row in data.iterrows():
                    class_name = str(row["MOC_Name"]).strip()
                    param_name = str(row["Parameter_Name"]).strip()
                    abbreviation = str(row["Abbreviation"]).strip() if pd.notna(row["Abbreviation"]) else param_name
                    data_type = str(row["Data_Type"]).strip()
                    mod_status = str(row["Modification"]).strip().lower()
                    required = str(row["Required_On_Creation"]).strip().lower()
                    required_col_ab = str(row["Required_On_Creation_Col_AB"]).strip().lower() if pd.notna(row["Required_On_Creation_Col_AB"]) else required
                    parent = str(row["Parent_Parameter"]).strip() if pd.notna(row["Parent_Parameter"]) else None
                    min_occurs = str(row["MinOccurs"]).strip() if pd.notna(row["MinOccurs"]) else ""
                    max_occurs = str(row["MaxOccurs"]).strip() if pd.notna(row["MaxOccurs"]) else ""

                    if (param_name.lower() == "parameter name" or
                        class_name.lower() in ['nan', 'none', ''] or
                        param_name.lower() in ['nan', 'none', ''] or
                        not class_name or not param_name or
                        class_name == 'nan' or param_name == 'nan'):
                        continue

                    if "bts" in mod_status:
                        color = "red"
                    elif "on-line" in mod_status:
                        color = "green"
                    elif "not modifiable" in mod_status:
                        color = "gray"
                    else:
                        color = "black"

                    if "mandatory" in required_col_ab:
                        mand = "(M)"
                    elif "optional" in required_col_ab:
                        mand = "(O)"
                    elif "system" in required_col_ab or "value set by" in required_col_ab:
                        mand = "(S)"
                    else:
                        mand = ""

                    uml_data[class_name]["attributes"].append({
                        "name": abbreviation,
                        "type": data_type,
                        "mandatory": mand,
                        "color": color,
                        "parent": parent
                    })

                    if "/" in class_name:
                        parts = class_name.split("/")
                        for i in range(1, len(parts)):
                            parent_class = "/".join(parts[:i])
                            child_class = "/".join(parts[:i + 1])
                            uml_data[parent_class]["relationships"].add(child_class)

                            multiplicity = ""
                            if min_occurs and min_occurs.lower() != 'nan' and max_occurs and max_occurs.lower() != 'nan':
                                multiplicity = f"{min_occurs}..{max_occurs}"
                            elif min_occurs and min_occurs.lower() != 'nan':
                                multiplicity = f"{min_occurs}..*"
                            elif max_occurs and max_occurs.lower() != 'nan':
                                multiplicity = f"0..{max_occurs}"

                            if multiplicity:
                                uml_data[parent_class]["multiplicities"][child_class] = multiplicity

                    all_classes.add(class_name)

        return sorted(all_classes)
    except Exception as e:
        print(f"Error loading UML data: {e}")
        return []


# ----------------- Routes: Parameter UI -----------------
@app.route('/parameter.html')
def parameter_page():
    if 'uploaded_files' not in session or not session['uploaded_files']:
        return redirect(url_for('landing_page'))
    return render_template('parameter.html')


@app.route('/get-parameters')
def get_parameters():
    try:
        # Return abbreviations (parameters_list)
        if not parameters_list:
            return jsonify({
                "error": "No parameters loaded. Upload an Excel file first.",
                "parameters": []
            }), 500
        return jsonify({"parameters": parameters_list})
    except Exception as e:
        return jsonify({"error": str(e), "parameters": []}), 500


@app.route('/get-relation', methods=['POST'])
def get_relation():
    """
    DEPENDENT (forward):
        Row where Column D == P → Column P contains dependent parameters.
        Uses BFS with dependent_depth.

    DEPENDENCY (backward):
        Row where cleaned P contains P → Column D is a dependency.
        ALWAYS direct — no depth, no recursion.

    INDIRECT:
        Start from (direct dependents ∪ direct dependencies).
        For indirect_depth loops:
            For each X in frontier:
                add direct dependents(X)
                add direct dependencies(X)
    """
    try:
        data = request.get_json()

        P = data.get("parameter", "").strip()
        dependent_depth = int(data.get("dependent_depth", 1))
        indirect_depth = int(data.get("indirect_depth", 1))

        if not P:
            return jsonify({"error": "No parameter provided"}), 400

        file_paths = session.get('uploaded_files', [])
        if not file_paths:
            return jsonify({"error": "No Excel files uploaded"}), 400

        # Final output sets
        dependent_set = set()
        dependency_set = set()
        indirect_set = set()

        # --- Column P cleaner ---
        def extract_related(cell):
            if pd.isna(cell):
                return []
            s = str(cell).strip()
            if not s:
                return []
            items = []
            for part in s.split(";"):
                part = part.strip()
                if not part:
                    continue
                part = re.sub(r"::.*$", "", part)     # remove ::public etc.
                if "-" in part:
                    part = part.split("-")[-1].strip()
                if part:
                    items.append(part)
            return items

        # ---------------- PROCESS ALL FILES ----------------
        for excel_path in file_paths:

            df = pd.read_excel(excel_path, engine='openpyxl')
            if df.shape[1] < 16:
                continue

            col_D = df.columns[3]
            col_P = df.columns[15]

            df["_P_clean"] = df[col_P].apply(extract_related)

            # =====================================================
            # 1️⃣ DIRECT DEPENDENT (forward)
            # =====================================================
            direct_dependents = set()
            rows = df[df[col_D].astype(str).str.strip() == P][col_P]

            for val in rows:
                direct_dependents |= set(extract_related(val))

            # BFS using dependent_depth
            visited = {P}
            frontier = {P}

            for _ in range(dependent_depth):
                new_frontier = set()
                for param in frontier:
                    rows2 = df[df[col_D].astype(str).str.strip() == param][col_P]
                    for v in rows2:
                        for dep in extract_related(v):
                            if dep not in visited:
                                visited.add(dep)
                                dependent_set.add(dep)
                                new_frontier.add(dep)
                if not new_frontier:
                    break
                frontier = new_frontier

            # =====================================================
            # 2️⃣ DIRECT DEPENDENCY (backward NO DEPTH)
            # =====================================================
            rows2 = df[df["_P_clean"].apply(lambda arr: P in arr)][col_D]

            for val in rows2:
                cleaned = str(val).strip()
                if cleaned:
                    dependency_set.add(cleaned)

            # =====================================================
            # 3️⃣ INDIRECT = BFS using indirect_depth
            # =====================================================
            start_points = direct_dependents | dependency_set

            visited_indirect = set(start_points)
            frontier_indirect = set(start_points)

            for _ in range(indirect_depth):
                next_frontier = set()
                for X in frontier_indirect:

                    # dependents of X
                    rowsX = df[df[col_D].astype(str).str.strip() == X][col_P]
                    for v in rowsX:
                        for dep in extract_related(v):
                            if dep not in visited_indirect:
                                visited_indirect.add(dep)
                                indirect_set.add(dep)
                                next_frontier.add(dep)

                    # dependencies of X
                    rowsX2 = df[df["_P_clean"].apply(lambda arr: X in arr)][col_D]
                    for v in rowsX2:
                        cleaned = str(v).strip()
                        if cleaned and cleaned not in visited_indirect:
                            visited_indirect.add(cleaned)
                            indirect_set.add(cleaned)
                            next_frontier.add(cleaned)

                if not next_frontier:
                    break

                frontier_indirect = next_frontier

        # Final cleanup
        indirect_set -= dependent_set
        indirect_set -= dependency_set
        indirect_set.discard(P)

        return jsonify({
            "dependent": sorted(dependent_set),
            "dependency": sorted(dependency_set),
            "indirect": sorted(indirect_set)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/reload-data', methods=['POST'])
def reload_data():
    try:
        file_paths = session.get('uploaded_files', [])
        if not file_paths:
            return jsonify({"success": False, "error": "No files uploaded"}), 400

        load_excel_data(file_paths)
        return jsonify({
            "success": True,
            "message": f"Data reloaded. Found {len(parameters_list)} abbreviations."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/test-data')
def test_data():
    file_paths = session.get('uploaded_files', [])
    return jsonify({
        "parameters_count": len(parameters_list),
        "relations_count": len(parameter_relations),
        "sample_parameters": parameters_list[:5] if parameters_list else [],
        "uploaded_files": file_paths
    })


# ----------------- UML UI -----------------
@app.route('/umldiagram.html')
def uml_ui():
    if 'uploaded_files' not in session or not session['uploaded_files']:
        return redirect(url_for('landing_page'))
    return render_template('umldiagram.html')


@app.route('/upload-main', methods=['POST'])
def upload_main():
    """Handle file upload from main page and store in session"""
    try:
        uploaded_files = request.files.getlist("excel_files")
        diagram_type = request.form.get('diagram_type', 'uml')
        available_files = request.form.getlist('available_files')

        if not uploaded_files and not available_files:
            return jsonify({"success": False, "error": "No files selected"}), 400

        if 'session_id' not in session:
            import uuid
            session['session_id'] = str(uuid.uuid4())

        session_dir = os.path.join(app.config['TEMP_FOLDER'], session['session_id'])
        os.makedirs(session_dir, exist_ok=True)
        file_paths = []

        # Process newly uploaded files
        for file in uploaded_files:
            if file and file.filename.endswith(('.xlsx', '.xls', '.xlsm')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(session_dir, filename)
                file.save(file_path)
                file_paths.append(file_path)
                # Copy to global uploads folder for listing
                global_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                shutil.copy2(file_path, global_path)

        # Process selected available files (copy to session)
        for filename in available_files:
            if filename and filename.endswith(('.xlsx', '.xls', '.xlsm')):
                safe_filename = secure_filename(filename)
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
                if os.path.exists(source_path):
                    dest_path = os.path.join(session_dir, safe_filename)
                    shutil.copy2(source_path, dest_path)
                    file_paths.append(dest_path)

        if not file_paths:
            return jsonify({"success": False, "error": "No valid Excel files found"}), 400

        session['uploaded_files'] = file_paths
        session['diagram_type'] = diagram_type

        # Load data based on diagram type
        if diagram_type == 'uml':
            load_uml_data(file_paths)
            load_excel_data(file_paths)  # Also load parameter data with ALL files
            return jsonify({"success": True, "redirect": url_for('uml_ui')})
        else:
            load_excel_data(file_paths)
            return jsonify({"success": True, "redirect": url_for('parameter_page')})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/select-available-files', methods=['POST'])
def select_available_files():
    """Handle selection of available files without upload"""
    try:
        data = request.get_json()
        selected_filenames = data.get('filenames', [])
        diagram_type = data.get('diagram_type', 'uml')

        if not selected_filenames:
            return jsonify({"success": False, "error": "No files selected"}), 400

        if 'session_id' not in session:
            import uuid
            session['session_id'] = str(uuid.uuid4())

        session_dir = os.path.join(app.config['TEMP_FOLDER'], session['session_id'])
        os.makedirs(session_dir, exist_ok=True)
        file_paths = []

        # Copy selected files to session directory
        for filename in selected_filenames:
            if filename and filename.endswith(('.xlsx', '.xls', '.xlsm')):
                safe_filename = secure_filename(filename)
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
                if os.path.exists(source_path):
                    dest_path = os.path.join(session_dir, safe_filename)
                    shutil.copy2(source_path, dest_path)
                    file_paths.append(dest_path)

        if not file_paths:
            return jsonify({"success": False, "error": "No valid files found"}), 400

        session['uploaded_files'] = file_paths
        session['diagram_type'] = diagram_type

        if diagram_type == 'uml':
            load_uml_data(file_paths)
            load_excel_data(file_paths)
            return jsonify({
                "success": True,
                "message": "Files loaded successfully.",
                "redirect": "/umldiagram.html"
            })
        else:
            load_excel_data(file_paths)
            return jsonify({
                "success": True,
                "message": f"Files loaded successfully. Found {len(parameters_list)} abbreviations.",
                "redirect": "/parameter.html"
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ----------------- Uploads to /uploads -----------------
@app.route('/upload-to-folder', methods=['POST'])
def upload_to_folder():
    """Handle file uploads to the uploads folder from the plus button"""
    try:
        uploaded_files = request.files.getlist("files")

        if not uploaded_files:
            return jsonify({"success": False, "error": "No files uploaded"}), 400

        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)

        uploaded_count = 0
        for file in uploaded_files:
            if file and file.filename.endswith(('.xlsx', '.xls', '.xlsm')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)
                uploaded_count += 1

        if uploaded_count == 0:
            return jsonify({"success": False, "error": "No valid Excel files found"}), 400

        return jsonify({
            "success": True,
            "message": f"{uploaded_count} file(s) uploaded successfully"
        })
    except Exception as e:
        print(f"Error uploading files: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/delete-all-files', methods=['DELETE'])
def delete_all_files():
    """Delete all files from the uploads folder"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            return jsonify({"success": False, "error": "Upload folder not found"}), 404

        deleted_count = 0
        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(('.xls', '.xlsx', '.xlsm')):
                os.remove(file_path)
                deleted_count += 1

        return jsonify({
            "success": True,
            "message": f"{deleted_count} file(s) deleted successfully"
        })
    except Exception as e:
        print(f"Error deleting all files: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/delete-file', methods=['DELETE'])
def delete_file():
    """Delete a single file from the uploads folder"""
    try:
        data = request.get_json()
        filename = data.get('filename')

        if not filename:
            return jsonify({"success": False, "error": "No filename provided"}), 400

        safe_filename = secure_filename(filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)

        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "File not found"}), 404

        if not safe_filename.lower().endswith(('.xls', '.xlsx', '.xlsm')):
            return jsonify({"success": False, "error": "Invalid file type"}), 400

        os.remove(file_path)

        return jsonify({
            "success": True,
            "message": f"File '{safe_filename}' deleted successfully"
        })
    except Exception as e:
        print(f"Error deleting file: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ----------------- UML class loading for UI -----------------
@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle UML diagram generation using session files"""
    global uml_data

    file_paths = session.get('uploaded_files', [])
    if not file_paths:
        return jsonify({
            "success": False,
            "error": "No files found in session. Please upload files from the main page."
        }), 400

    # If UML data not already loaded, load it
    if not uml_data:
        classes = load_uml_data(file_paths)
        classes_data = [{"value": cls, "label": cls.split("/")[-1]} for cls in classes]
        classes_with_all = [{"value": "All Classes", "label": "All Classes"}] + classes_data
        return jsonify({"success": True, "classes": classes_with_all})

    else:
        all_classes = sorted(uml_data.keys())
        classes_data = [{"value": cls, "label": cls.split("/")[-1]} for cls in all_classes]
        classes_with_all = [{"value": "All Classes", "label": "All Classes"}] + classes_data
        return jsonify({"success": True, "classes": classes_with_all})


# ----------------- UML Diagram Generation -----------------
@app.route('/uml', methods=['POST'])
def generate_uml():
    data = request.get_json()
    selected_class = data.get("parameter")
    depth = int(data.get("depth", 1))

    if not selected_class:
        return jsonify({"uml": "graph TD\n%% No class selected", "class_count": 0})

    if selected_class == "All Classes":
        return generate_all_classes_uml()

    if selected_class not in uml_data:
        return jsonify({"uml": "graph TD\n%% Invalid class selected", "class_count": 0})

    visited = set()
    result_classes = {}
    queue = deque()
    queue.append((selected_class, 0))

    while queue:
        current_cls, current_depth = queue.popleft()
        if current_cls in visited or current_depth > depth:
            continue

        visited.add(current_cls)
        result_classes[current_cls] = uml_data[current_cls]

        if current_depth < depth:
            for rel in uml_data[current_cls]["relationships"]:
                queue.append((rel, current_depth + 1))

    lines = ["graph TD"]

    for cls, info in result_classes.items():
        safe_cls = create_safe_node_id(cls)
        display_name = sanitize_for_mermaid(cls.split("/")[-1])
        
        # Center-aligned class name
        label_lines = [f"<div style='text-align:center;'><b>{display_name}</b></div>", "<hr>"]

        attributes = info["attributes"]
        visible_attrs = attributes[:MAX_VISIBLE_ATTRIBUTES]
        hidden_count = len(attributes) - MAX_VISIBLE_ATTRIBUTES

        # Left-aligned attributes with padding
        for attr in visible_attrs:
            attr_name = sanitize_for_mermaid(attr['name'])
            attr_type = sanitize_for_mermaid(attr['type'])
            attr_mand = sanitize_for_mermaid(attr['mandatory'])
            if not attr_name or attr_name == 'nan':
                continue
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:{attr['color']}'>+ {attr_name} : {attr_type} {attr_mand}</span></div>")

        if hidden_count > 0:
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:#3b82f6;font-weight:600;font-style:italic'>... +{hidden_count} more attributes</span></div>")

        html_label = "<br>".join(label_lines).replace('"', '#quot;')
        lines.append(f'{safe_cls}["{html_label}"]')

    for cls, info in result_classes.items():
        from_cls = create_safe_node_id(cls)
        for rel in info["relationships"]:
            if rel in result_classes:
                to_cls = create_safe_node_id(rel)
                multiplicity = info["multiplicities"].get(rel, "")
                if multiplicity:
                    multiplicity = sanitize_for_mermaid(multiplicity)
                    lines.append(f'{from_cls} -->|{multiplicity}| {to_cls}')
                else:
                    lines.append(f"{from_cls} --> {to_cls}")

    return jsonify({"uml": "\n".join(lines), "class_count": len(result_classes)})

def generate_all_classes_uml():
    if not uml_data:
        return jsonify({"uml": "graph TD\n%% No classes available", "class_count": 0})

    lines = ["graph TD"]

    for cls, info in uml_data.items():
        safe_cls = create_safe_node_id(cls)
        display_name = sanitize_for_mermaid(cls.split("/")[-1])
        
        # Center-aligned class name
        label_lines = [f"<div style='text-align:center;'><b>{display_name}</b></div>", "<hr>"]

        attributes = info["attributes"]
        visible_attrs = attributes[:MAX_VISIBLE_ATTRIBUTES]
        hidden_count = len(attributes) - MAX_VISIBLE_ATTRIBUTES

        # Left-aligned attributes with padding
        for attr in visible_attrs:
            attr_name = sanitize_for_mermaid(attr['name'])
            attr_type = sanitize_for_mermaid(attr['type'])
            attr_mand = sanitize_for_mermaid(attr['mandatory'])
            if not attr_name or attr_name == 'nan':
                continue
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:{attr['color']}'>+ {attr_name} : {attr_type} {attr_mand}</span></div>")

        if hidden_count > 0:
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:#3b82f6;font-weight:600;font-style:italic'>... +{hidden_count} more attributes</span></div>")

        html_label = "<br>".join(label_lines).replace('"', '#quot;')
        lines.append(f'{safe_cls}["{html_label}"]')

    for cls, info in uml_data.items():
        from_cls = create_safe_node_id(cls)
        for rel in info["relationships"]:
            if rel in uml_data:
                to_cls = create_safe_node_id(rel)
                multiplicity = info["multiplicities"].get(rel, "")
                if multiplicity:
                    multiplicity = sanitize_for_mermaid(multiplicity)
                    lines.append(f'{from_cls} -->|{multiplicity}| {to_cls}')
                else:
                    lines.append(f"{from_cls} --> {to_cls}")

    return jsonify({"uml": "\n".join(lines), "class_count": len(uml_data)})

@app.route('/download-pdf', methods=['POST'])
def download_pdf():
    try:
        data = request.get_json()
        image_data = data.get('imageData')
        class_name = data.get('className', 'uml_diagram')
        
        if not image_data:
            return jsonify({"success": False, "error": "No image data provided"}), 400
        
        # Remove data URL prefix if present
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        image_buffer = BytesIO(image_bytes)
        
        # Create PDF in memory
        pdf_buffer = BytesIO()
        
        # Use landscape A4 for better diagram visibility
        page_width, page_height = landscape(A4)
        
        # Create canvas
        c = canvas.Canvas(pdf_buffer, pagesize=landscape(A4))
        
        # Get image dimensions
        img = ImageReader(BytesIO(image_bytes))
        img_width, img_height = img.getSize()
        
        # Calculate scaling to fit page with margins
        margin = 50
        available_width = page_width - (2 * margin)
        available_height = page_height - (2 * margin)
        
        # Scale image to fit page while maintaining aspect ratio
        scale_width = available_width / img_width
        scale_height = available_height / img_height
        scale = min(scale_width, scale_height)
        
        scaled_width = img_width * scale
        scaled_height = img_height * scale
        
        # Center the image on the page
        x = (page_width - scaled_width) / 2
        y = (page_height - scaled_height) / 2
        
        # Draw the image
        c.drawImage(img, x, y, width=scaled_width, height=scaled_height)
        
        # Add title at the top
        c.setFont("Helvetica-Bold", 16)
        title = f"UML Class Diagram - {class_name}"
        c.drawCentredString(page_width / 2, page_height - 30, title)
        
        # Add timestamp at the bottom
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.setFont("Helvetica", 10)
        c.drawCentredString(page_width / 2, 20, f"Generated on {timestamp}")
        
        # Save PDF
        c.save()
        
        # Get PDF bytes
        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()
        
        # Encode to base64 for sending to frontend
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        return jsonify({
            "success": True,
            "pdf": pdf_base64,
            "filename": f"uml_diagram_{class_name}.pdf"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
# ----------------- Session / Home -----------------
@app.route('/clear-session', methods=['POST'])
def clear_session():
    try:
        if 'session_id' in session:
            folder = os.path.join(app.config['TEMP_FOLDER'], session['session_id'])
            if os.path.exists(folder):
                shutil.rmtree(folder)

        session.clear()
        parameters_list.clear()
        parameter_relations.clear()
        uml_data.clear()
        abbrev_to_param.clear()
        param_to_abbrev.clear()

        return jsonify({"success": True, "message": "Session cleared"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/')
def landing_page():
    return render_template('main.html')


@app.route('/get-available-files')
def get_available_files():
    try:
        files = []
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)

        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(('.xls', '.xlsx', '.xlsm')):
                files.append({
                    "name": filename,
                    "size": os.path.getsize(file_path)
                })
        return jsonify({"success": True, "files": files})
    except Exception as e:
        print(f"Error getting available files: {e}")
        return jsonify({"success": False, "files": [], "error": str(e)})


if __name__ == '__main__':
    app.run(debug=True)