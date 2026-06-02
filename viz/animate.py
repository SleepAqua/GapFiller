import plotly.graph_objects as go
import pandas as pd

def build_animation(results, out_html='results.html'):
    # results: dict strategy -> list of {chunk, cumulative_mean}
    df_list = []
    for name, rows in results.items():
        for r in rows:
            df_list.append({'strategy': name, 'chunk': r['chunk'], 'mean': r['cumulative_mean']})
    df = pd.DataFrame(df_list)
    df = df.sort_values(['chunk','strategy'])
    chunks = sorted(df['chunk'].unique())

    # initial frame
    init = df[df['chunk']==chunks[0]]
    fig = go.Figure(
        data=[go.Bar(x=init['strategy'], y=init['mean'])],
        layout=go.Layout(title='Cumulative mean score by strategy',
                         yaxis=dict(range=[0, df['mean'].max()*1.1])),
        frames=[]
    )

    frames = []
    for c in chunks:
        sub = df[df['chunk']==c]
        frames.append(go.Frame(data=[go.Bar(x=sub['strategy'], y=sub['mean'])], name=str(c)))

    fig.frames = frames
    # slider
    fig.update_layout(
        updatemenus=[dict(type='buttons', showactive=False,
                          y=1, x=1.1, xanchor='right', yanchor='top',
                          pad=dict(t=0, r=10),
                          buttons=[dict(label='Play', method='animate',
                                        args=[None, {'frame': {'duration': 200, 'redraw': True}, 'fromcurrent': True}])])],
        sliders=[dict(steps=[dict(method='animate', args=[[f.name], {'mode': 'immediate', 'frame': {'duration': 0}}], label=f.name) for f in frames],
                      transition={'duration': 0}, x=0, y=0, currentvalue={'prefix': 'Chunk: '})]
    )

    fig.write_html(out_html, auto_open=False)
    return out_html
