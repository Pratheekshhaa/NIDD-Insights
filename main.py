from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
import os
from collections import defaultdict, deque
import tempfile
import shutil

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMP_FOLDER'] = 'temp_uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)

parameters_list = []
parameter_relations = {}
uml_data = defaultdict(lambda: {
    "attributes": [],
    "relationships": set(),
    "multiplicities": {}
})

# --------- Parameter Relation Finder (NEW LOGIC) ---------
def detect_header(df, search_columns):
    """Auto-detect header row by looking for columns that contain 'Parameter' or similar keywords"""
    for i in range(min(10, len(df))):  # Check first 10 rows
        row = df.iloc[i].astype(str).str.lower()
        if any(keyword in row[j] for keyword in search_columns for j in range(len(row))):
            return i
    return 0  # fallback

def load_excel_data(file_paths):
    """Load parameter data from multiple Excel files using column D (index 3) for input and P (index 15) for relations"""
    global parameters_list, parameter_relations
    try:
        parameters_list = []
        parameter_relations = {}

        for file_path in file_paths:
            df_sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl', header=None)

            for sheet_name, df in df_sheets.items():
                if df.shape[1] < 16:
                    continue

                header_row = detect_header(df, search_columns=["parameter", "relation"])
                df.columns = df.iloc[header_row]
                df = df.iloc[header_row + 1:].reset_index(drop=True)

                col_d, col_p = df.columns[3], df.columns[15]
                df_clean = df.dropna(subset=[col_d], how='all')

                for _, row in df_clean.iterrows():
                    param_name = str(row[col_d]).strip() if pd.notna(row[col_d]) else ""
                    related_params = str(row[col_p]).strip() if pd.notna(row[col_p]) else ""

                    if not param_name or param_name.lower() == 'nan':
                        continue

                    if param_name not in parameters_list:
                        parameters_list.append(param_name)

                    if related_params and related_params.lower() != 'nan':
                        existing = parameter_relations.get(param_name, [])
                        if isinstance(existing, str):
                            existing = [] if existing == "No related parameters found" else [existing]
                        new_rels = [r.strip() for r in related_params.split(";") if r.strip()]
                        parameter_relations[param_name] = list(set(existing + new_rels))
                    else:
                        if param_name not in parameter_relations:
                            parameter_relations[param_name] = "No related parameters found"

        parameters_list.sort()
    except Exception as e:
        print(f"Failed to load Excel: {e}")

# --------- UML Diagram Generator (UPDATED WITH MULTIPLICITY) ---------
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
                    data.columns[4]: "Data_Type",
                    data.columns[5]: "Parent_Parameter",
                    data.columns[25]: "Required_On_Creation",
                    data.columns[28]: "Modification",
                    data.columns[29]: "MinOccurs",
                    data.columns[30]: "MaxOccurs"
                })
                
                data = data.dropna(subset=["MOC_Name", "Parameter_Name"], how='all')
                
                for _, row in data.iterrows():
                    class_name = str(row["MOC_Name"]).strip()
                    param_name = str(row["Parameter_Name"]).strip()
                    data_type = str(row["Data_Type"]).strip()
                    mod_status = str(row["Modification"]).strip().lower()
                    required = str(row["Required_On_Creation"]).strip().lower()
                    parent = str(row["Parent_Parameter"]).strip() if pd.notna(row["Parent_Parameter"]) else None
                    min_occurs = str(row["MinOccurs"]).strip() if pd.notna(row["MinOccurs"]) else ""
                    max_occurs = str(row["MaxOccurs"]).strip() if pd.notna(row["MaxOccurs"]) else ""
                    
                    # Skip invalid entries
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
                        color = "gray"
                        
                    mand = "(M)" if "mandatory" in required else "(O)" if "optional" in required else ""
                    
                    uml_data[class_name]["attributes"].append({
                        "name": param_name,
                        "type": data_type,
                        "mandatory": mand,
                        "color": color,
                        "parent": parent
                    })
                    
                    if "/" in class_name:
                        parts = class_name.split("/")
                        for i in range(1, len(parts)):
                            parent_class = "/".join(parts[:i])
                            child_class = "/".join(parts[:i+1])
                            uml_data[parent_class]["relationships"].add(child_class)
                            
                            # Store multiplicity for this relationship
                            multiplicity = ""
                            if min_occurs and min_occurs.lower() != 'nan' and max_occurs and max_occurs.lower() != 'nan':
                                multiplicity = f"{min_occurs}..{max_occurs}"
                            elif min_occurs and min_occurs.lower() != 'nan':
                                multiplicity = f"{min_occurs}..*"
                            elif max_occurs and max_occurs.lower() != 'nan':
                                multiplicity = f"0..{max_occurs}"
                            
                            if multiplicity:
                                if child_class not in uml_data[parent_class]["multiplicities"]:
                                    uml_data[parent_class]["multiplicities"][child_class] = multiplicity
                            
                    all_classes.add(class_name)
        
        return sorted(all_classes)
    except Exception as e:
        print(f"Error loading UML data: {e}")
        return []

@app.route('/parameter.html')
def parameter_page():
    if 'uploaded_files' not in session or not session['uploaded_files']:
        return redirect(url_for('landing_page'))
    return render_template('parameter.html')

@app.route('/get-parameters')
def get_parameters():
    try:
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
    """NEW LOGIC - Returns direct and indirect relations with 4-level traversal"""
    try:
        data = request.get_json()
        param = data.get("parameter", "").strip()
        if not param:
            return jsonify({"error": "No parameter provided"}), 400

        file_paths = session.get('uploaded_files', [])
        if not file_paths:
            return jsonify({"error": "No Excel files uploaded"}), 400

        direct_relations = set()
        all_indirect = set()

        for excel_path in file_paths:
            # Read with automatic header detection (first row as header)
            df = pd.read_excel(excel_path, engine="openpyxl")
            if df.shape[1] < 16:
                continue

            # Use column D (index 3) and column P (index 15)
            col_d, col_p = df.columns[3], df.columns[15]
            
            # Find direct relations for the parameter
            direct_relations.update([
                r.strip()
                for rel in df.loc[df[col_d].astype(str).str.strip() == param, col_p].dropna().tolist()
                for r in str(rel).split(";") if r and r.strip() and r.strip().lower() != 'nan'
            ])

            # Find indirect relations (4-level deep traversal)
            visited = set([param])
            level_relations = set([param])

            for _ in range(4):
                new_relations = set()
                for current in level_relations:
                    matches = df[df[col_p].astype(str).str.contains(current, na=False)][col_d].dropna().tolist()
                    for rel in matches:
                        for r in str(rel).split(";"):
                            r = r.strip()
                            if r and r.lower() != 'nan' and r not in visited:
                                new_relations.add(r)
                if not new_relations:
                    break
                visited.update(new_relations)
                all_indirect.update(new_relations)
                level_relations = new_relations
        return jsonify({"direct": sorted(direct_relations), "indirect": sorted(all_indirect - {param})})
    except Exception as e:
        import traceback
        print(f"Error in get_relation: {e}")
        print(traceback.format_exc())
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
            "message": f"Data reloaded. Found {len(parameters_list)} parameters."
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

# --------- UML Diagram Generator (UPDATED WITH MULTIPLICITY) ---------
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

        session_id = session.get('session_id')
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
        session_dir = os.path.join(app.config['TEMP_FOLDER'], session_id)
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
            classes = load_uml_data(file_paths)
            load_excel_data(file_paths)  # Also load parameter data with ALL files
            return jsonify({"success": True, "redirect": url_for('uml_ui')})
        else:
            load_excel_data(file_paths)  # Load ALL files for parameters
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

        session_id = session.get('session_id')
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
        session_dir = os.path.join(app.config['TEMP_FOLDER'], session_id)
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

        # Load data based on diagram type
        if diagram_type == 'uml':
            classes = load_uml_data(file_paths)
            load_excel_data(file_paths)  # Also load parameter data with ALL files
            return jsonify({
                "success": True,
                "message": f"Files loaded successfully. Found {len(classes)} classes.",
                "redirect": "/umldiagram.html"
            })
        else:
            load_excel_data(file_paths)  # Load ALL files for parameters
            return jsonify({
                "success": True,
                "message": f"Files loaded successfully. Found {len(parameters_list)} parameters.",
                "redirect": "/parameter.html"
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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

@app.route('/delete-file', methods=['DELETE'])
def delete_file():
    try:
        # You're sending ?name=filename.xlsx in the query
        file_name = request.args.get('name')
        if not file_name:
            return jsonify({"success": False, "error": "No filename provided"}), 400

        # Secure filename to avoid path traversal
        safe_name = secure_filename(file_name)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)

        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "File not found"}), 404

        os.remove(file_path)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting file: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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
        # Add "All Classes" option at the beginning
        classes_with_all = ["All Classes"] + classes
        return jsonify({
            "success": True,
            "classes": classes_with_all
        })
    else:
        all_classes = sorted(uml_data.keys())
        # Add "All Classes" option at the beginning
        classes_with_all = ["All Classes"] + all_classes
        return jsonify({
            "success": True,
            "classes": classes_with_all
        })

@app.route('/uml', methods=['POST'])
def generate_uml():
    data = request.get_json()
    selected_class = data.get("parameter")
    depth = int(data.get("depth", 1))
    
    if not selected_class:
        return jsonify({"uml": "graph TD\n%% No class selected"})

    # Handle "All Classes" selection
    if selected_class == "All Classes":
        return generate_all_classes_uml()
    
    if selected_class not in uml_data:
        return jsonify({"uml": "graph TD\n%% Invalid class selected"})

    visited = set()
    result_classes = {}
    queue = deque()
    
    # KEY FIX: Only start from the selected class (leaf), don't include parent hierarchy
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
        safe_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        
        # KEY FIX: Extract only the leaf class name for display
        display_name = cls.split("/")[-1] if "/" in cls else cls
        
        label_lines = [f"<b>{display_name}</b>", "<hr>"]

        for attr in info["attributes"]:
            label = f"<span style='color:{attr['color']}'>+ {attr['name']} : {attr['type']} {attr['mandatory']}</span>"
            label_lines.append(label)

        html_label = "<br>".join(label_lines).replace('"', '&quot;')
        lines.append(f'{safe_cls}["{html_label}"]')

    for cls, info in result_classes.items():
        from_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        for rel in info["relationships"]:
            if rel in result_classes:
                to_cls = rel.replace("/", "_").replace("-", "_").replace(".", "_")
                # Add multiplicity if available
                multiplicity = info["multiplicities"].get(rel, "")
                if multiplicity:
                    lines.append(f'{from_cls} -->|"{multiplicity}"| {to_cls}')
                else:
                    lines.append(f"{from_cls} --> {to_cls}")

    return jsonify({"uml": "\n".join(lines)})

def generate_all_classes_uml():
    """Generate UML diagram for all classes - showing only leaf names"""
    if not uml_data:
        return jsonify({"uml": "graph TD\n%% No classes available"})

    lines = ["graph TD"]

    # Add all classes with their attributes
    for cls, info in uml_data.items():
        safe_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        
        # KEY FIX: Extract only the leaf class name for display
        display_name = cls.split("/")[-1] if "/" in cls else cls
        
        label_lines = [f"<b>{display_name}</b>", "<hr>"]

        for attr in info["attributes"]:
            label = f"<span style='color:{attr['color']}'>+ {attr['name']} : {attr['type']} {attr['mandatory']}</span>"
            label_lines.append(label)
            
        html_label = "<br>".join(label_lines).replace('"', '&quot;')
        lines.append(f'{safe_cls}["{html_label}"]')

    # Add all relationships with multiplicity
    for cls, info in uml_data.items():
        from_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        for rel in info["relationships"]:
            if rel in uml_data:  # Only add relationship if target class exists
                to_cls = rel.replace("/", "_").replace("-", "_").replace(".", "_")
                # Add multiplicity if available
                multiplicity = info["multiplicities"].get(rel, "")
                if multiplicity:
                    lines.append(f'{from_cls} -->|"{multiplicity}"| {to_cls}')
                else:
                    lines.append(f"{from_cls} --> {to_cls}")

    return jsonify({"uml": "\n".join(lines)})


@app.route('/clear-session', methods=['POST'])
def clear_session():
    try:
        session_id = session.get('session_id')
        if session_id:
            session_dir = os.path.join(app.config['TEMP_FOLDER'], session_id)
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir)
                
        session.clear()
        global parameters_list, parameter_relations, uml_data
        parameters_list = []
        parameter_relations = {}
        uml_data.clear()
        return jsonify({"success": True, "message": "Session cleared"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --------- Main Entry ---------
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