import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file, Response
from datetime import datetime
import io
from weasyprint import HTML  # Import WeasyPrint

app = Flask(__name__)

# --- Configuration & Helper Functions ---
DATA_FILE = 'packing_data.json'

BOX_TYPES = {
    "Type 1 (Square)": {"L": 52, "W": 52, "H": 40},
    "Type 2 (Tall Large)": {"L": 44, "W": 44, "H": 60},
    "Type 3 (Rectangle)": {"L": 52, "W": 30, "H": 30}
}

# NEW: Store addresses in dictionaries
FROM_ADDRESS = {
    "name": "John Doe",
    "line1": "Apartment 802, Satin House",
    "line2": "7 Fresco Walk",
    "city": "London",
    "country": "United Kingdom",
    "postcode": "E1 8PW"
}

TO_ADDRESS = {
    "name": "John Doe",
    "line1": "Jl. Pantai Batu Bolong,",
    "line2": "Gg. Bantan No.11C",
    "city_province": "Badung, Bali",
    "area": "Kuta Utara",
    "postcode": "80361"
}


def calculate_volumetric_weight(dims):
    return (dims["L"] * dims["W"] * dims["H"]) / 5000

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
        if box_name and box_name not in data:
            data[box_name] = {"type": box_type, "items": []}
            save_data(data)
        return redirect(url_for('index'))
    
    sorted_box_names = sorted(data.keys(), key=lambda x: int(''.join(filter(str.isdigit, x))) if any(char.isdigit() for char in x) else float('inf'))
    
    boxes_with_details = []
    for box_name in sorted_box_names:
        box_info = data[box_name]
        
        if isinstance(box_info, dict):
            box_type = box_info.get("type", "N/A")
            item_count = len(box_info.get("items", []))
            volumetric_weight = 0
            if box_type in BOX_TYPES:
                dims = BOX_TYPES[box_type]
                volumetric_weight = calculate_volumetric_weight(dims)
            weight_str = f"{volumetric_weight:.2f} kg"
        else:
            box_type, item_count, weight_str = "N/A (Legacy)", len(box_info), "N/A"

        boxes_with_details.append({'name': box_name, 'count': item_count, 'type': box_type, 'weight': weight_str})
    
    return render_template('index.html', boxes=boxes_with_details, box_types=BOX_TYPES.keys())


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

# ... (edit_item, delete_item, delete_box routes remain the same) ...
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


# NEW: Route to export to PDF
@app.route('/export_pdf/<box_name>')
def export_pdf(box_name):
    data = load_data()
    box_info = data.get(box_name)
    if not box_info: return redirect(url_for('index'))
    
    items, volumetric_weight_str, total_qty = [], "N/A", 0
    if isinstance(box_info, dict):
        items = box_info.get('items', [])
        box_type = box_info.get("type", "N/A")
        total_qty = sum(item['quantity'] for item in items)
        if box_type in BOX_TYPES:
            weight = calculate_volumetric_weight(BOX_TYPES[box_type])
            volumetric_weight_str = f"{weight:.2f} kg"
    else:
        items = box_info
        total_qty = sum(item['quantity'] for item in items)

    # Render the HTML template with data
    rendered_html = render_template(
        'pdf_template.html',
        box_name=box_name,
        current_date=datetime.now().strftime('%d/%m/%Y'),
        from_address=FROM_ADDRESS,
        to_address=TO_ADDRESS,
        items=items,
        total_qty=total_qty,
        volumetric_weight_str=volumetric_weight_str
    )

    # Generate PDF from HTML
    pdf = HTML(string=rendered_html).write_pdf()

    # Create a Flask response with the PDF
    return Response(pdf,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment;filename={box_name}_Packing_List.pdf'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)