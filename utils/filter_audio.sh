melt  -video-track data/videos/tammy/Oceans_1.mp4 -audio-track data/videos/tammy/Oceans_1.mp4 -attach-track ladspa.1403 0=−25 1=0.25 2=0.4 3=0.6  -attach-track ladspa.1913 0=17 1=−3 2=0.5 -attach-track ladspa.dsp fir=~/.config/ladspa_dsp/sensimetrics_impulse_response_1012_LR.wav  -consumer avformat:test2.mp4 acodec=libmp3lame ab=256k vcodec=libx264 b=5000k
