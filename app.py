import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file, Response
from datetime import datetime
import io
from weasyprint import HTML
import math # Import the math library for rounding

app = Flask(__name__)

# --- Configuration & Helper Functions ---
DATA_FILE = 'packing_data.json'

BOX_TYPES = {
    "Type 1 (Square)": {"L": 52, "W": 52, "H": 40},
    "Type 2 (Tall Large)": {"L": 44, "W": 44, "H": 60},
    "Type 3 (Rectangle)": {"L": 52, "W": 30, "H": 30}
}

FROM_ADDRESS = {
    "name": "John Doe", "line1": "Apartment 802, Satin House", "line2": "7 Fresco Walk",
    "city": "London", "country": "United Kingdom", "postcode": "E1 8PW"
}

TO_ADDRESS = {
    "name": "John Doe", "line1": "Jl. Pantai Batu Bolong,", "line2": "Gg. Bantan No.11C",
    "city_province": "Badung, Bali", "area": "Kuta Utara", "postcode": "80361"
}

def calculate_volumetric_weight(dims):
    """Calculates volumetric weight and ALWAYS rounds up."""
    return math.ceil((dims["L"] * dims["W"] * dims["H"]) / 5000)

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r') as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    data = load_data()
    if request.method == 'POST':
        box_name = request.form['box_name'].strip()
        box_type = request.form['box_type']
        # Get actual weight from form, default to 0 if empty
        actual_weight = request.form.get('actual_weight', 0)
        
        if box_name and box_name not in data:
            data[box_name] = {
                "type": box_type, 
                "items": [],
                "actual_weight": float(actual_weight) if actual_weight else 0
            }
            save_data(data)
        return redirect(url_for('index'))
    
    sorted_box_names = sorted(data.keys(), key=lambda x: int(''.join(filter(str.isdigit, x))) if any(char.isdigit() for char in x) else float('inf'))
    
    boxes_with_details = []
    for box_name in sorted_box_names:
        box_info = data[box_name]
        
        if isinstance(box_info, dict):
            box_type = box_info.get("type", "N/A")
            item_count = len(box_info.get("items", []))
            actual_weight = box_info.get("actual_weight", 0)
            volumetric_weight = 0
            if box_type in BOX_TYPES:
                dims = BOX_TYPES[box_type]
                volumetric_weight = calculate_volumetric_weight(dims)
            weight_str = f"{volumetric_weight} kg" # Now an integer
        else:
            box_type, item_count, weight_str, actual_weight = "N/A (Legacy)", len(box_info), "N/A", 0

        boxes_with_details.append({
            'name': box_name, 
            'count': item_count, 
            'type': box_type, 
            'volumetric_weight': weight_str,
            'actual_weight': f"{actual_weight} kg"
        })
    
    return render_template('index.html', boxes=boxes_with_details, box_types=BOX_TYPES.keys())

# ... (view_box, edit_item, delete_item, delete_box routes remain mostly the same) ...
@app.route('/box/<box_name>', methods=['GET', 'POST'])
def view_box(box_name):
    data = load_data()
    if box_name not in data: return redirect(url_for('index'))
    box_content = data[box_name]
    box_items_list = box_content.get('items', []) if isinstance(box_content, dict) else box_content
    if request.method == 'POST':
        if isinstance(box_content, dict):
            new_item = {'item': request.form['item'], 'description': request.form['description'], 'quantity': int(request.form['quantity'])}
            box_content['items'].append(new_item)
            save_data(data)
        return redirect(url_for('view_box', box_name=box_name))
    return render_template('box_view.html', box_name=box_name, items=box_items_list)

@app.route('/edit/<box_name>/<int:item_index>', methods=['GET', 'POST'])
def edit_item(box_name, item_index):
    data = load_data()
    box_content = data.get(box_name)
    if not box_content: return redirect(url_for('index'))
    items_list = box_content if isinstance(box_content, list) else box_content.get('items', [])
    if not 0 <= item_index < len(items_list): return redirect(url_for('view_box', box_name=box_name))
    item_to_edit = items_list[item_index]
    if request.method == 'POST':
        item_to_edit['item'] = request.form['item']
        item_to_edit['description'] = request.form['description']
        item_to_edit['quantity'] = int(request.form['quantity'])
        save_data(data)
        return redirect(url_for('view_box', box_name=box_name))
    return render_template('edit_item.html', box_name=box_name, item_index=item_index, item=item_to_edit)

@app.route('/delete/<box_name>/<int:item_index>')
def delete_item(box_name, item_index):
    data = load_data()
    box_content = data.get(box_name)
    if not box_content: return redirect(url_for('index'))
    items_list = box_content if isinstance(box_content, list) else box_content.get('items', [])
    if 0 <= item_index < len(items_list):
        del items_list[item_index]
        save_data(data)
    return redirect(url_for('view_box', box_name=box_name))

@app.route('/delete_box/<box_name>')
def delete_box(box_name):
    data = load_data()
    if box_name in data:
        del data[box_name]
        save_data(data)
    return redirect(url_for('index'))

def get_export_data(box_name):
    """Helper function to gather data for PDF and Print views."""
    data = load_data()
    box_info = data.get(box_name)
    if not box_info:
        return None

    items, vol_wt, act_wt, total_qty = [], 0, 0, 0
    
    if isinstance(box_info, dict):
        items = box_info.get('items', [])
        box_type = box_info.get("type", "N/A")
        act_wt = box_info.get("actual_weight", 0)
        total_qty = sum(item['quantity'] for item in items)
        if box_type in BOX_TYPES:
            vol_wt = calculate_volumetric_weight(BOX_TYPES[box_type])
    else:
        items = box_info
        total_qty = sum(item['quantity'] for item in items)

    return {
        "items": items,
        "total_qty": total_qty,
        "volumetric_weight_str": f"{vol_wt} kg",
        "actual_weight_str": f"{act_wt} kg"
    }

@app.route('/export_pdf/<box_name>')
def export_pdf(box_name):
    export_data = get_export_data(box_name)
    if not export_data: return redirect(url_for('index'))
    
    rendered_html = render_template('pdf_template.html', box_name=box_name, current_date=datetime.now().strftime('%d/%m/%Y'), from_address=FROM_ADDRESS, to_address=TO_ADDRESS, **export_data)
    pdf = HTML(string=rendered_html).write_pdf()
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename={box_name}_Packing_List.pdf'})

@app.route('/print/<box_name>')
def print_packing_slip(box_name):
    export_data = get_export_data(box_name)
    if not export_data: return redirect(url_for('index'))
    
    return render_template('print_template.html', box_name=box_name, current_date=datetime.now().strftime('%d/%m/%Y'), from_address=FROM_ADDRESS, to_address=TO_ADDRESS, **export_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)