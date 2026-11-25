# Element color packs

Open **View → Molecular appearance… → Import color pack…**, select a local JSON file and choose **Save**. OrcaView keeps an installed copy and remembers the selected scheme across restarts. To update a scheme, edit its source file, import it again with the same ID and save. To return to the original colors while keeping your model and sizes, select **OrcaView default**.

Start with [contrast.json](contrast.json). It changes carbon, nitrogen, oxygen, sulfur and chlorine. Each listed color applies to the 3D molecule and its element labels in the 2D sketch. Other elements retain their original colors in each view. Structure image exports use the active view's colors.

Stick and wireframe views darken very light colors so bonds to hydrogen and other pale elements stay visible on the light canvas.

| Field | Value |
| --- | --- |
| `id` | A unique ID starting with a lowercase ASCII letter, followed by lowercase letters, digits, hyphens or underscores. Maximum 48 characters. The built-in scheme reserves `default`. |
| `name` | A display name of 1–80 printable characters after trimming surrounding spaces. Unicode is supported. |
| `colors` | An object with at least one element symbol and its six-digit RGB color, such as `"Cl": "#087345"`. Symbols and hex digits are case-insensitive. Each of the 118 elements may appear once. |

Use these three fields in a UTF-8 JSON object up to 64 KiB. You can share the JSON file directly with another OrcaView user.
