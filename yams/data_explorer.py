import gradio as gr
import pandas as pd
import matplotlib.pyplot as plt

class DataExplorer():
    def __init__(self):
        self.df = None

    def interface(self):
        file = gr.File(file_types=['.csv'])

        with gr.Row():
            with gr.Column():
                x_lim_low = gr.Slider(label="x start")
                x_range = gr.Slider(label="x range", minimum=0, maximum=10000)

            with gr.Column():
                y_lim_low = gr.Slider(label='y_start', maximum=5e5)
                y_range = gr.Slider(label="y range", minimum=0, maximum=5e5)

        fig = gr.Plot()

        x_to_plot = gr.Radio(label="x data")
        y_to_plot = gr.CheckboxGroup(label="y data")

        btn = gr.Button()
        btn.click(self.update_figure, inputs=[x_to_plot, y_to_plot, x_lim_low, x_range, y_lim_low, y_range], outputs=fig)    

        file.change(self.process_file, inputs=file, outputs=[x_to_plot, y_to_plot, x_lim_low])

    def process_file(self, file):
        self.df = pd.read_csv(file)
        choices = list(self.df.columns)
        return [gr.Radio(choices, label="x data"), 
                gr.CheckboxGroup(choices, label="y data"), 
                gr.Slider(label="x start", maximum=len(self.df.index))]
    
    def update_figure(self, x_to_plot, y_to_plot, 
                      xlim, xrange,
                      ylim, yrange):
        print(y_to_plot)
        fig = plt.figure(figsize=[10, 4])
        for y in y_to_plot:
            plt.plot(self.df[x_to_plot], self.df[y], label=y)
        plt.legend()
        plt.xlim(xlim, xlim + xrange)
        plt.ylim(ylim, ylim + yrange)
        return fig


