from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.run import connections
from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType, ExpectedCredentials
from typing import Optional, List, Union, Any

# ── Upload mode ──────────────────────────────────────────────
#   "cos"          – IBM Cloud Object Storage only
#   "free"         – Free services only (catbox / tmpfiles)
#   "cos_fallback" – Try COS first, fall back to free services
UPLOAD_MODE = "free"

# Only declare cos_connection as expected when UPLOAD_MODE actually needs COS.
# WXO validates expected_credentials at invocation time — if the connection
# isn't configured with team credentials, any tool call will fail even if
# the code path never touches COS.
_expected_creds = []
if UPLOAD_MODE in ("cos", "cos_fallback"):
    _expected_creds = [ExpectedCredentials(
        app_id="cos_connection",
        type=ConnectionType.KEY_VALUE
    )]


@tool(expected_credentials=_expected_creds)
def generate_and_upload_chart(
        x_values: List[Any],
        y_values: List[Union[int, float]],
        chart_type: str = "bar",
        title: str = "",
        x_label: str = "",
        y_label: str = "",
        sort_data: bool = False,
        descending: bool = True
) -> str:
    """Generates a chart and uploads it to return a Markdown link.

    Creates visually appealing charts with automatic data handling and validation.
    Supports Hebrew/RTL text in titles. All chart labels should be in English.

    Args:
        x_values (list): X-axis values, e.g. ['A', 'B'].
        y_values (list): Y-axis values, e.g. [10, 20].
        chart_type (str, optional): Chart type - 'bar', 'line', 'pie', or 'scatter'. Defaults to 'bar'.
        title (str, optional): Chart title (can be Hebrew or English). Defaults to empty string.
        x_label (str, optional): X-axis label (English). Defaults to empty string.
        y_label (str, optional): Y-axis label (English). Defaults to empty string.
        sort_data (bool, optional): Whether to sort data by y_values. Defaults to False.
        descending (bool, optional): Sort order (only if sort_data=True). Defaults to True.

    Returns:
        str: Markdown formatted string with the uploaded chart image.

    Example of calling the tool:
        # Simple bar chart
        generate_and_upload_chart(x_values=['A', 'B'], y_values=[10, 20], title='Simple Bar')

        # Full example
        generate_and_upload_chart(
            x_values=['Product A', 'Product B', 'Product C'],
            y_values=[150, 230, 180],
            chart_type='bar',
            title='Sales Comparison',
            x_label='Products',
            y_label='Sales ($)'
        )
    Example output:
        ![Sales Comparison](https://catbox.moe/your_uploaded_image_url.png)
    """
    import matplotlib.pyplot as plt
    import matplotlib as mpl
    import seaborn as sns
    import pandas as pd
    from io import BytesIO
    import requests
    from bidi.algorithm import get_display

    def contains_hebrew(text):
        """Check if text contains Hebrew characters."""
        if not isinstance(text, str):
            text = str(text)
        return any('\u0590' <= c <= '\u05FF' for c in text)

    def process_rtl_text(text):
        """Process RTL/Hebrew text for proper display in matplotlib."""
        if not isinstance(text, str):
            text = str(text)
        if contains_hebrew(text):
            return get_display(text)
        return text

    try:
        # ===== INPUT VALIDATION AND AUTO-FIXING =====

        # Fix if single values were passed instead of lists
        if isinstance(x_values, dict) and 'root' in x_values:
            x_values = x_values['root']
        if isinstance(y_values, dict) and 'root' in y_values:
            y_values = y_values['root']

        if not isinstance(x_values, (list, tuple)):
            x_values = [x_values]
        if not isinstance(y_values, (list, tuple)):
            y_values = [y_values]

        # Convert all values to lists if they're not already
        x_values = list(x_values)
        y_values = list(y_values)

        # Remove None values
        valid_pairs = [(x, y) for x, y in zip(x_values, y_values) if x is not None and y is not None]
        if not valid_pairs:
            return "❌ Error: No valid data points provided. Both x_values and y_values must contain valid data."

        x_values, y_values = zip(*valid_pairs)
        x_values = list(x_values)
        y_values = list(y_values)

        # Convert y_values to numeric
        try:
            cleaned_y = []
            for y in y_values:
                # Handle potentially "dirty" numeric strings
                if isinstance(y, str):
                    y = y.replace(",", "").replace("$", "").replace("€", "").strip()
                cleaned_y.append(float(y))
            y_values = cleaned_y
        except (ValueError, TypeError) as e:
            # Try to identify the bad value for better error message
            bad_val = "unknown"
            for y in y_values:
                try:
                    if isinstance(y, str):
                        float(y.replace(",", "").replace("$", "").replace("€", "").strip())
                    else:
                        float(y)
                except:
                    bad_val = f"{y}"
                    break
            return (f"❌ Error: y_values must contain numeric values. Failed on: {bad_val}\n"
                    f"Expected input example: generate_and_upload_chart(x_values=['A', 'B'], y_values=[10, 20], title='Simple Bar')")

        # Check minimum data points
        if len(x_values) < 2:
            return "❌ Error: Chart requires at least 2 data points."

        # Validate chart type
        valid_chart_types = ['bar', 'line', 'pie', 'scatter', 'barh']
        chart_type = chart_type.lower().strip()
        if chart_type not in valid_chart_types:
            chart_type = 'bar'  # Default fallback

        # ===== DATA PREPARATION =====

        # Create DataFrame
        df = pd.DataFrame({
            'x': x_values,
            'y': y_values
        })

        # Sort if requested
        if sort_data:
            df = df.sort_values('y', ascending=not descending)

        # Limit to 50 data points
        if len(df) > 50:
            step = max(1, len(df) // 50)
            df = df.iloc[::step].head(50)

        # ===== CONFIGURE MATPLOTLIB FOR HEBREW =====
        mpl.rcParams['font.family'] = 'DejaVu Sans'

        # ===== PROCESS HEBREW TEXT FOR DISPLAY =====
        # Convert x_values to proper RTL display format
        x_labels_display = [process_rtl_text(x) for x in df['x']]

        # ===== CREATE CHART =====
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.set_style("whitegrid")

        # Create colors with highlight for top value
        colors = ['#3498db'] * len(df)
        if len(df) > 1:
            max_idx = df['y'].idxmax()
            colors[df.index.get_loc(max_idx)] = '#e74c3c'

        if chart_type == 'bar':
            ax.bar(range(len(df)), df['y'], color=colors)
            ax.set_xticks(range(len(df)))
            ax.set_xticklabels(x_labels_display, rotation=45, ha='right')

        elif chart_type == 'barh':
            ax.barh(range(len(df)), df['y'], color=colors)
            ax.set_yticks(range(len(df)))
            ax.set_yticklabels(x_labels_display)

        elif chart_type == 'line':
            ax.plot(range(len(df)), df['y'], marker='o', linewidth=2,
                    markersize=8, color='#3498db')
            ax.set_xticks(range(len(df)))
            ax.set_xticklabels(x_labels_display, rotation=45, ha='right')

        elif chart_type == 'scatter':
            ax.scatter(range(len(df)), df['y'], s=100, color=colors, alpha=0.6)
            ax.set_xticks(range(len(df)))
            ax.set_xticklabels(x_labels_display, rotation=45, ha='right')

        elif chart_type == 'pie':
            # Process pie chart labels for Hebrew
            ax.pie(df['y'], labels=x_labels_display, autopct='%1.1f%%',
                   startangle=90, colors=plt.cm.Set3(range(len(df))))
            ax.axis('equal')

        # Remove spines (not for pie chart)
        if chart_type != 'pie':
            sns.despine(left=True, bottom=True)

        # ===== SET LABELS AND TITLE =====
        if title:
            # Handle Hebrew text in title
            title_display = process_rtl_text(title)
            ax.set_title(title_display, fontsize=14, fontweight='bold', pad=20)

        if x_label and chart_type != 'pie':
            # X and Y labels should typically be in English, but process anyway
            x_label_display = process_rtl_text(x_label)
            ax.set_xlabel(x_label_display, fontsize=12)

        if y_label and chart_type != 'pie':
            y_label_display = process_rtl_text(y_label)
            ax.set_ylabel(y_label_display, fontsize=12)

        # Adjust layout
        plt.tight_layout()

        # ===== SAVE TO BYTES =====
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_bytes = buffer.read()
        plt.close(fig)

        # ===== UPLOAD IMAGE =====
        def _upload_cos(img_bytes):
            import uuid
            wx_conn = connections.key_value("cos_connection")
            api_key = wx_conn.get("COS_API_KEY") or wx_conn.get("COS_APIKEY")
            instance_crn = wx_conn.get("COS_INSTANCE_CRN")
            endpoint = wx_conn.get("COS_ENDPOINT")
            public_endpoint = wx_conn.get("COS_PUBLIC_ENDPOINT") or endpoint
            bucket = wx_conn.get("COS_BUCKET") or wx_conn.get("COS_BUCKET_NAME")
            if not all([api_key, instance_crn, endpoint, bucket]):
                return None
            token_resp = requests.post(
                "https://iam.cloud.ibm.com/identity/token",
                data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
                headers={"Accept": "application/json"},
                timeout=15,
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]
            object_key = f"charts/{uuid.uuid4().hex}.png"
            upload_url = f"{endpoint.rstrip('/')}/{bucket}/{object_key}"
            put_resp = requests.put(
                upload_url,
                data=img_bytes,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "image/png",
                    "x-amz-acl": "public-read",
                    "ibm-service-instance-id": instance_crn,
                },
                timeout=30,
            )
            put_resp.raise_for_status()
            return f"{public_endpoint.rstrip('/')}/{bucket}/{object_key}"

        def _upload_free(img_bytes):
            import base64
            # 1. Try litterbox.catbox.moe (temporary 72h hosting)
            try:
                resp = requests.post("https://litterbox.catbox.moe/resources/internals/api.php",
                    files={"fileToUpload": ("chart.png", img_bytes, "image/png")},
                    data={"reqtype": "fileupload", "time": "72h"}, timeout=30)
                resp.raise_for_status()
                url = resp.text.strip()
                if url.startswith("http"):
                    return url
            except Exception:
                pass
            # 2. Try freeimage.host (permanent, free API key)
            try:
                b64 = base64.b64encode(img_bytes).decode()
                resp = requests.post("https://freeimage.host/api/1/upload",
                    data={"key": "6d207e02198a847aa98d0a2a901485a5",
                          "source": b64, "format": "json"}, timeout=30)
                resp.raise_for_status()
                return resp.json()["image"]["url"]
            except Exception:
                pass
            return None

        if UPLOAD_MODE == "cos":
            image_url = _upload_cos(image_bytes)
        elif UPLOAD_MODE == "free":
            image_url = _upload_free(image_bytes)
        else:  # cos_fallback
            image_url = None
            try:
                image_url = _upload_cos(image_bytes)
            except Exception:
                pass
            if not image_url:
                image_url = _upload_free(image_bytes)

        if not image_url:
            return "❌ Error: Failed to upload chart image."

        markdown_link = f"![{title or 'Chart'}]({image_url})"
        return markdown_link

    except Exception as e:
        # Clean up matplotlib figure if it exists
        try:
            plt.close(fig)
        except:
            pass
        return f"❌ Error: Failed to generate or upload chart: {str(e)}"
