"""Render genuine province classification exports; no training/test markers."""
from pathlib import Path
import html
import json

import folium
from branca.element import MacroElement, Template

CLASS_NAMES={"Sawah":"Farmland","Pemukiman":"Built-up areas","Hutan Non-Mangrove":"Forest","Air":"Water bodies","Hutan Mangrove":"Mangrove forest"}
CLASS_CODES={"Sawah":1,"Pemukiman":2,"Hutan Non-Mangrove":3,"Air":4,"Hutan Mangrove":5}
COLORS={1:'#bcbd22',2:'#d62728',3:'#006400',4:'#1f77b4',5:'#2ca02c'}


class LocalFullscreen(MacroElement):
    _template=Template("""{% macro script(this, kwargs) %}
    (function(){
      var map={{ this._parent.get_name() }};
      var Control=L.Control.extend({options:{position:'topleft'},onAdd:function(){
        var box=L.DomUtil.create('div','leaflet-bar');
        var button=L.DomUtil.create('a','',box);
        button.href='#';button.title='Toggle full screen';button.setAttribute('aria-label','Toggle full screen');
        button.textContent='⛶';button.style.fontSize='22px';
        L.DomEvent.on(button,'click',function(e){L.DomEvent.stop(e);
          var el=map.getContainer();
          if(!document.fullscreenElement){if(el.requestFullscreen)el.requestFullscreen().catch(function(){});}
          else if(document.exitFullscreen){document.exitFullscreen();}
        });return box;
      }});
      map.addControl(new Control());
      document.addEventListener('fullscreenchange',function(){setTimeout(function(){map.invalidateSize();},100);});
    })();
    {% endmacro %}""")


def local_leaflet(map_view,base):
    assets=Path(base)/'map_assets'
    js_path=assets/'leaflet.js';css_path=assets/'leaflet.css'
    if not js_path.exists() or not css_path.exists():
        raise FileNotFoundError('Map assets missing. Extract the complete map-loading fix, including map_assets.')
    # Core Leaflet is bundled in the iframe itself; neither map controls nor
    # local classification images depend on external JavaScript CDNs.
    map_view.default_js=[];map_view.default_css=[]
    root=map_view.get_root()
    root.header.add_child(folium.Element('<style>'+css_path.read_text(encoding='utf-8')+'</style>'),name='local_leaflet_css')
    root.header.add_child(folium.Element('<script>'+js_path.read_text(encoding='utf-8')+'</script>'),name='local_leaflet_js')
    root.header.add_child(folium.Element("""<style>
      html,body{height:100%;width:100%;margin:0;padding:0;overflow:hidden;}
      .folium-map{position:absolute!important;inset:0!important;min-height:100%;}
      .leaflet-container{font-family:system-ui,sans-serif;background:#e6edf1;}
      .leaflet-control-layers{border:0!important;border-radius:10px;padding:9px 12px;box-shadow:0 4px 20px #0003;}
      .leaflet-bar{border-radius:8px;overflow:hidden;}
      .leaflet-tooltip{border-radius:8px;}
    </style>"""),name='map_control_style')
    return map_view


def render_classification(base,selected,opacity=.7,show_samples=False):
    base=Path(base);folder=base/'province_classification'
    manifest=json.loads((folder/'manifest.json').read_text())
    if not manifest.get('complete'):raise ValueError('Province classification has not finished.')
    m=local_leaflet(folium.Map(location=[-7.4,112.9],tiles=None,zoom_start=7,control_scale=True),base)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles © Esri — Esri, Maxar, Earthstar Geographics and the GIS User Community',name='Esri satellite').add_to(m)
    folium.TileLayer('OpenStreetMap',name='OpenStreetMap',show=False).add_to(m)
    study=json.loads((folder/'study_area.geojson').read_text())
    folium.GeoJson(study,name='Classification study boundary',show=False,style_function=lambda f:{'color':'#14b8a6','weight':1,'fillOpacity':0}).add_to(m)
    counts={str(code):sum(t['counts'][str(code)] for t in manifest['tiles']) for code in COLORS}
    total=manifest['valid_pixels']
    for cls in selected:
        code=CLASS_CODES[cls];pct=counts[str(code)]/total*100 if total else 0
        layer=folium.FeatureGroup(name=f'{CLASS_NAMES[cls]} · {pct:.2f}%',show=True)
        for tile in manifest['tiles']:
            for item in tile['images']:
                if item['class_code']!=code:continue
                path=(folder/item['path']).resolve()
                if not path.is_relative_to(folder.resolve()):raise ValueError('Invalid classification asset path.')
                if not path.exists():raise FileNotFoundError(f'Missing class image: {item["path"]}')
                folium.raster_layers.ImageOverlay(image=str(path),bounds=item['bounds'],opacity=opacity,interactive=False,zindex=4).add_to(layer)
        layer.add_to(m)
    samples_path=base/'samples.geojson'
    if samples_path.exists():
        samples=json.loads(samples_path.read_text())
        for index,feature in enumerate(samples['features']):
            props=feature.get('properties') or {}
            polygon_id=str(props.get('poligon_id') or feature.get('id') or f'sample_{index}')
            # Folium can use a unique property as a JavaScript identifier.
            # Keep internal keys identifier-safe; friendly text belongs in aliases.
            feature['id']=polygon_id
            feature['properties']={
                'polygon_id':polygon_id,
                'land_cover':CLASS_NAMES.get(props.get('label_teks'),props.get('label_teks')),
            }
        folium.GeoJson(samples,name='Reference sample polygons',show=show_samples,
            style_function=lambda f:{'color':'#ffffff','weight':1.3,'fillOpacity':0},
            tooltip=folium.GeoJsonTooltip(fields=['polygon_id','land_cover'],aliases=['Polygon ID','Digitized class'])).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m);LocalFullscreen().add_to(m)
    west,south,east,north=manifest['bounds'];m.fit_bounds([[south,west],[north,east]],padding=(20,20))
    lines=''.join(f'<div style="margin-top:5px"><i style="display:inline-block;width:9px;height:9px;background:{COLORS[CLASS_CODES[c]]};border-radius:2px;margin-right:6px"></i>{html.escape(CLASS_NAMES[c])} <span style="color:#64748b">{counts[str(CLASS_CODES[c])]/total*100:.2f}%</span></div>' for c in selected)
    legend=f'''<div style="position:fixed;bottom:30px;left:14px;z-index:9999;background:rgba(255,255,255,.95);color:#172b3a;padding:12px 15px;border-radius:12px;box-shadow:0 4px 18px #0003;font:12px system-ui;max-width:240px"><b>East Java land cover</b>{lines}<div style="font-size:10px;color:#64748b;margin-top:9px">{manifest['settings']['resolution_m']} m grid · {total:,} valid pixels<br>Percentages exclude missing data</div></div>'''
    m.get_root().html.add_child(folium.Element(legend))
    # Signal readiness and expose JavaScript initialization errors in the map,
    # instead of leaving a blank panel with only a static legend.
    m.get_root().header.add_child(folium.Element("""<script>
    window.addEventListener('error',function(event){
        var box=document.getElementById('map-init-error');
        if(!box){box=document.createElement('div');box.id='map-init-error';
          box.style.cssText='position:fixed;top:12px;left:12px;right:12px;z-index:99999;background:#fff1f2;color:#881337;padding:12px;border-radius:10px;font:13px system-ui';
          document.body.appendChild(box);}
        box.textContent='Map initialization error: '+String(event.message).slice(0,180);
    });
    </script>"""),name='map_error_display')
    return m.get_root().render()
