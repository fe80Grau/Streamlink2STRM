from flask import send_file, redirect, stream_with_context, Response
from sanitize_filename import sanitize
import os
from clases.config import config as c
from clases.worker import worker as w
from clases.folders import folders as f
from clases.nfo import nfo as n
from plugins.crunchyroll.jellyfin import daemon
import subprocess
from threading import Thread

## -- CRUNCHYROLL CLASS
class Crunchyroll:
    def __init__(self, channel=False):
        if channel:
            self.channel = channel.replace("https://www.crunchyroll.com/","")
            self.channel_url = "https://www.crunchyroll.com/{}".format(self.channel)
            self.channel_folder = self.channel.split('/')[-1]
            self.last_episode_file = "{}/{}/{}.{}".format(
                media_folder, 
                sanitize(
                    "{}".format(
                        self.channel_folder
                    )
                ), 
                "last_episode", 
                "txt"
            )
            self.new_content = False
            self.last_episode = self.get_start_episode()
            self.videos = self.get_videos()
    
    def get_videos(self):
        command = [
            'yt-dlp', 
            '--print', '%(season_number)s;%(season)s;%(episode_number)s;%(episode)s;%(webpage_url)s;%(playlist_autonumber)s', 
            '--no-download',
            '--no-warnings',
            '--match-filter', 'language={}'.format(audio_language),
            '--extractor-args', 'crunchyrollbeta:hardsub={}'.format(subtitle_language),
            '{}'.format(self.channel_url),
            '--replace-in-metadata', '"season,episode"', '"[;/]"', '"-"'
        ]
        
        self.set_auth(command)
        self.set_proxy(command)
        self.set_start_episode(command)
        #print(' '.join(command))
        return w.worker(command).pipe() 

    def get_start_episode(self):
        last_episode = 0
        if not os.path.isfile(self.last_episode_file):
            self.new_content = True
            f.folders().write_file(self.last_episode_file, "0")
        else:
            with open(self.last_episode_file) as fl:
                last_episode = fl.readlines()
                fl.close()
            
            last_episode = last_episode[0]
        
        return last_episode

    def set_start_episode(self, command):
        if not self.new_content:
            try:
                next_episode = int(self.last_episode)
            except:
                next_episode = 1
            if next_episode < 1:
                next_episode = 1
            command.append('--playlist-start')
            command.append('{}'.format(next_episode))

    def set_last_episode(self, playlist_count):
        if self.new_content:
            f.folders().write_file(
                self.last_episode_file, 
                playlist_count
            )
        else:
            #sum_episode = int(self.last_episode) + int(playlist_count)
            f.folders().write_file(
                self.last_episode_file,
                str(playlist_count)
            )

    def set_auth(self, command, quotes=False):
        if config['crunchyroll_auth'] == "browser":
            command.append('--cookies-from-browser')
            if quotes:
                command.append(
                    '"{}"'.format(
                        config['crunchyroll_browser']
                    )
                )
            else:
                command.append(config['crunchyroll_browser'])

        if config['crunchyroll_auth'] == "cookies":
            command.append('--cookies')
            command.append(config['crunchyroll_cookies_file'])

        if config['crunchyroll_auth'] == "login":
            command.append('--username')
            command.append(config['crunchyroll_username'])
            command.append('--password')
            command.append(config['crunchyroll_password'])

        command.append('--user-agent')
        if quotes:
            command.append(
                '"{}"'.format(
                    config['crunchyroll_useragent']
                )
            )
        else:
            command.append(
                '{}'.format(
                    config['crunchyroll_useragent']
                )
            )

    def set_proxy(self, command):
        if proxy:
            if proxy_url != "":
                command.append('--proxy')
                command.append(proxy_url)

## -- END

## -- LOAD CONFIG AND CHANNELS FILES
ytdlp2strm_config = c.config(
    './config/config.json'
).get_config()

config = c.config(
    './plugins/crunchyroll/config.json'
).get_config()

channels = c.config(
    config["channels_list_file"]
).get_channels()

source_platform = "crunchyroll"
media_folder = config["strm_output_folder"]
channels_list = config["channels_list_file"]
cookies_file = config["crunchyroll_cookies_file"]
subtitle_language = config["crunchyroll_subtitle_language"]
audio_language = config['crunchyroll_audio_language']
jellyfin_preload = False
jellyfin_preload_last_episode = False

if 'jellyfin_preload' in config:
    jellyfin_preload = bool(config['jellyfin_preload'])
if 'jellyfin_preload_last_episode' in config:
    jellyfin_preload_last_episode = bool(config['jellyfin_preload_last_episode'])
if 'proxy' in config:
    proxy = config['proxy']
    proxy_url = config['proxy_url']
else:
    proxy = False
    proxy_url = ""
## -- END

## -- JELLYFIN DAEMON
if jellyfin_preload:
    Thread(target=daemon, daemon=True).start()
## -- END

## -- MANDATORY TO_STRM FUNCTION 
def to_strm(method):
    for crunchyroll_channel in channels:
        print("Preparing channel {}".format(crunchyroll_channel))

        crunchyroll = Crunchyroll(crunchyroll_channel)
        #crunchyroll.get_cookie_from_firefox()

        # -- MAKES CHANNEL DIR (AND SUBDIRS) IF NOT EXIST, REMOVE ALL STRM IF KEEP_OLDER_STRM IS SETTED TO FALSE IN GENERAL CONFIG
        f.folders().make_clean_folder(
            "{}/{}".format(
                media_folder,  
                sanitize(
                    "{}".format(
                        crunchyroll.channel_folder
                    )
                )
            ),
            False,
            config
        )
        ## -- END

        # -- BUILD STRM
        process = crunchyroll.videos
        file_content = ""
        try:
            for line in iter(process.stdout.readline, b''):
                if line != "" and not 'ERROR' in line and not 'WARNING' in line:
                    #print(line)
                    season_number = str(line).rstrip().split(';')[0].zfill(2)
                    season = str(line).rstrip().split(';')[1]
                    episode_number = (line).rstrip().split(';')[2].zfill(4)
                    episode = (line).rstrip().split(';')[3]
                    url = (line).rstrip().split(';')[4].replace(
                        'https://www.crunchyroll.com/',
                        ''
                    ).replace('/','_')
                    playlist_count = (line).rstrip().split(';')[5]
               
                    if not episode_number == '0' and not episode_number  == 0:

                        video_name = "{} - {}".format(
                            "S{}E{}".format(
                                season_number, 
                                episode_number
                            ), 
                            episode
                        )

                        file_content = "http://{}:{}/{}/{}/{}".format(
                            ytdlp2strm_config['ytdlp2strm_host'], 
                            ytdlp2strm_config['ytdlp2strm_port'], 
                            source_platform, 
                            method, 
                            url
                        )

                        file_path = "{}/{}/{}/{}.{}".format(
                            media_folder,  
                            sanitize(
                                "{}".format(
                                    crunchyroll.channel_folder
                                )
                            ),  
                            sanitize(
                                "S{} - {}".format(
                                    season_number, 
                                    season
                                )
                            ), 
                            sanitize(video_name), 
                            "strm"
                        )

                        f.folders().make_clean_folder(
                            "{}/{}/{}".format(
                                media_folder,  
                                sanitize(
                                    "{}".format(
                                        crunchyroll.channel_folder
                                    )
                                ),  
                                sanitize(
                                    "S{} - {}".format(
                                        season_number, 
                                        season
                                    )
                                )
                            ),
                            False,
                            config
                        )

                        if not os.path.isfile(file_path):
                            f.folders().write_file(
                                file_path, 
                                file_content
                            )

                        if crunchyroll.new_content:
                            crunchyroll.set_last_episode(playlist_count)
                        else:
                            #print(int(playlist_count))
                            try:
                                sum_episode = int(crunchyroll.last_episode) + int(playlist_count)
                            except:
                                try:
                                    sum_episode = 1 + int(playlist_count)
                                except:
                                    sum_episode = 1
                            #print(int(crunchyroll.last_episode))
                            #print(sum_episode)
                            crunchyroll.set_last_episode(
                                str(sum_episode)
                            )

                if not line:
                    if jellyfin_preload_last_episode:
                        if 'http' in file_content:
                            w.worker(file_content).preload()
                    break
                
        finally:
            process.kill()
        ## -- END
    return True 
## -- END

## -- EXTRACT / REDIRECT VIDEO DATA 

def direct(crunchyroll_id): 
    '''
    command = [
        'yt-dlp', 
        '-f', 'best',
        '--no-warnings',
        '--match-filter', '"language={}"'.format(audio_language),
        '--extractor-args', '"crunchyrollbeta:hardsub={}"'.format(subtitle_language),
        'https://www.crunchyroll.com/{}'.format(crunchyroll_id.replace('_','/')),
        '--get-url'
    ]
    Crunchyroll().set_auth(command,True)
    Crunchyroll().set_proxy(command)
    crunchyroll_url = w.worker(command).output()
    return redirect(crunchyroll_url, code=301)
    '''

    return download(crunchyroll_id)

def download(crunchyroll_id):

    current_dir = os.getcwd()

    # Construyes la ruta hacia la carpeta 'temp' dentro del directorio actual
    temp_dir = os.path.join(current_dir, 'temp')
    def extract_media(command):
        #print(' '.join(command))
        subprocess.run(command)

    def preprocess_video(input_video, input_audio, output_file):
        """Pre-procesa el video y el audio para optimizarlo para streaming."""
        cmd = [
            'ffmpeg',
            '-y',
            '-i', input_video,
            '-i', input_audio,
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            output_file
        ]
        subprocess.run(cmd, check=True)
    
    if not os.path.isfile(os.path.join(temp_dir, f'crunchyroll-{crunchyroll_id}.mp4')):
        command_video = [
            'yt-dlp', 
            '-f', 'bestvideo',
            '--no-warnings',
            '--extractor-args', 'crunchyrollbeta:hardsub={}'.format(subtitle_language),
            '--external-downloader', 'aria2c',
            '--external-downloader-args', '-j 16 -x 16 -k 1M',
            'https://www.crunchyroll.com/{}'.format(crunchyroll_id.replace('_','/')),
            '--output', os.path.join(temp_dir, f'{crunchyroll_id}.mp4')
        ]
        Crunchyroll().set_auth(command_video,False)
        Crunchyroll().set_proxy(command_video)


        command_audio = [
            'yt-dlp', 
            '-f', 'bestaudio',
            '--no-warnings',
            '--match-filter', 'language={}'.format(audio_language),
            '--extractor-args', 'crunchyrollbeta:hardsub={}'.format(subtitle_language),
            '--external-downloader', 'aria2c',
            '--external-downloader-args', '-j 16 -x 16 -k 1M',
            'https://www.crunchyroll.com/{}'.format(crunchyroll_id.replace('_','/')),
            '--output', os.path.join(temp_dir, f'{crunchyroll_id}.m4a')
        ]
        Crunchyroll().set_auth(command_audio,False)
        Crunchyroll().set_proxy(command_audio)

        video = Thread(target=extract_media, args=(command_video,))
        audio = Thread(target=extract_media, args=(command_audio,))

        video.start()
        audio.start()

        video.join()
        audio.join()

        preprocess_video(
            os.path.join(temp_dir, f'{crunchyroll_id}.mp4'), 
            os.path.join(temp_dir, f'{crunchyroll_id}.m4a'), 
            os.path.join(temp_dir, f'crunchyroll-{crunchyroll_id}.mp4')
        )

    return send_file(
        os.path.join(temp_dir, f'crunchyroll-{crunchyroll_id}.mp4')
    )
    #return stream_video(f'{crunchyroll_id}.mp4', f'{crunchyroll_id}.m4a')

#experimental not works.
def remux(crunchyroll_id):

    def remux_stream_to_hls():
        hls_output = '-'  # Ejemplo de ruta de salida, asumiendo una carpeta 'static' en tu aplicación Flask.
        command_ffmpeg = [
            'ffmpeg',
            '-i', 'pipe:0',  # Entrada de video (ej. 'pipe:0')
            '-i', 'pipe:1',  # Entrada de audio (ej. 'pipe:1')
            '-c:v', 'copy',  # Copiar el stream de vídeo sin recodificar
            '-c:a', 'aac',  # Codificar el stream de audio a AAC
            '-f', 'hls',  # Formato de salida HLS
            '-hls_time', '2',  # Duración de cada segmento de HLS en segundos
            '-hls_playlist_type', 'event',  # O 'live' para streaming en vivo
            '-hls_segment_filename', 'static/live%03d.ts',  # Patrón de nombre de archivo de segmento
            hls_output  # Archivo de manifiesto HLS
        ]
        process_ffmpeg = subprocess.Popen(command_ffmpeg, stdout=subprocess.PIPE, bufsize=10**8)

        def read_stream(process):
            # Leemos el stdout del proceso de ffmpeg en bucles de 4096 bytes
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    process.terminate()  # Asegúrate de terminar el proceso si ya no hay datos
                    break
                yield chunk

        return read_stream(process_ffmpeg)
    
    def generate_video_stream():
        # Configura los comandos de yt-dlp para video y audio
        command_video = [
            'yt-dlp',
            '--no-warnings',
            '--external-downloader', 'aria2c',
            '--match-filter', 'language={}'.format(audio_language),
            '--extractor-args', 'crunchyrollbeta:hardsub={}'.format(subtitle_language),
            '--output', '-',  # Salida al stdout
            f'https://www.crunchyroll.com/{crunchyroll_id.replace("_", "/")}',
        ]
        Crunchyroll().set_auth(command_video,False)
        Crunchyroll().set_proxy(command_video)

        command_audio = [
            'yt-dlp',
            '--no-warnings',
            '--format', 'ba',  # Selecciona el mejor vídeo combinado con el mejor audio
            '--external-downloader', 'aria2c',
            '--match-filter', 'language={}'.format(audio_language),
            '--extractor-args', 'crunchyrollbeta:hardsub={}'.format(subtitle_language),
            '--output', '-',  # Salida al stdout
            f'https://www.crunchyroll.com/{crunchyroll_id.replace("_", "/")}',
        ]
        Crunchyroll().set_auth(command_audio,False)
        Crunchyroll().set_proxy(command_audio)
        # Ejecuta yt-dlp para obtener los flujos combinados de video y audio
        process_video = subprocess.Popen(command_video, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process_audio = subprocess.Popen(command_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


        return Response(stream_with_context(remux_stream_to_hls()), mimetype='video/x-matroska')

    return generate_video_stream()

## -- END