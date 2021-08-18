import numpy as np
import warnings

from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.mixture import BayesianGaussianMixture
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning

from skimage.transform import resize
from skimage.color.adapt_rgb import adapt_rgb, each_channel
from skimage.color import rgb2hsv, hsv2rgb
from skimage.color import rgb2lab, deltaE_ciede2000
from skimage.filters import sobel as skimage_sobel
from skimage.exposure import equalize_adapthist
from skimage.morphology import square as skimage_square
from skimage.morphology import dilation as skimage_dilation
from skimage.filters import median as skimage_median
from skimage.util import view_as_blocks

from scipy.ndimage import convolve

from .pal import BasePalette

class BGM(BayesianGaussianMixture):
    """Wrapper for BayesianGaussianMixture"""
    MAX_ITER = 128
    RANDOM_STATE = 1234
    
    def __init__(self, palette, find_palette):
        """Init BGM with different default parameters depending on use-case"""
        self.palette = palette
        self.find_palette = find_palette
        if self.find_palette:
            super().__init__(n_components=self.palette,
                    max_iter=self.MAX_ITER,
                    covariance_type="tied",
                    weight_concentration_prior_type="dirichlet_distribution",  
                    weight_concentration_prior=1. / self.palette, 
                    mean_precision_prior=1. / 256.,
                    warm_start=False,
                    random_state=self.RANDOM_STATE)
        else:
            super().__init__(n_components=len(self.palette),
                    max_iter=self.MAX_ITER,
                    covariance_type="tied",
                    weight_concentration_prior_type="dirichlet_process",  
                    weight_concentration_prior=1e-7,
                    mean_precision_prior=1. / len(self.palette),
                    warm_start=False,
                    random_state=self.RANDOM_STATE)
            self.mean_prior = np.mean([val[0] for val in self.palette], axis=0)
    
    def _initialize_parameters(self, X, random_state):
        """Changes init parameters from K-means to CIE LAB distance when palette is assigned"""
        assert self.init_params == "kmeans", "Initialization is overwritten, can only be set as 'kmeans'."
        n_samples, _ = X.shape
        resp = np.zeros((n_samples, self.n_components))
        if self.find_palette:
            # original
            label = KMeans(n_clusters=self.n_components, n_init=1,
                                   random_state=random_state).fit(X).labels_
        else:
            # color distance
            label = np.argmin([deltaE_ciede2000(rgb2lab(X), rgb2lab(p), kH=3, kL=2) for p in self.palette], axis=0)
        resp[np.arange(n_samples), label] = 1
        self._initialize(X, resp)
        
    def fit(self, X, y=None):
        """Fits BGM model but alters convergence warning"""
        converged = True
        with warnings.catch_warnings(record=True) as w:
            super().fit(X)
            if w and w[-1].category == ConvergenceWarning:
                warnings.filterwarnings("ignore", category=ConvergenceWarning)
                converged = False
        if not converged:
            warnings.warn("Pyxelate could not properly assign colors, try a different palette size for better results!", Warning)
        return self
    
    def predict_proba(self, X):
        p = super().predict_proba(X)
        if self.find_palette:
            if self.palette < 3:
                return np.sqrt(p)
        elif len(self.palette) < 3:
            return np.sqrt(p)
        return p


class Pyx(BaseEstimator, TransformerMixin):
    """Pyx extends scikit-learn transformers"""
    
    BGM_RESIZE = 256
    SCALE_RGB = 1.07
    HIST_BRIGHTNESS = 1.19
    COLOR_QUANT = 8
    DITHER_AUTO_SIZE_LIMIT_HI = 512
    DITHER_AUTO_SIZE_LIMIT_LO = 16
    DITHER_AUTO_COLOR_LIMIT = 8
    DITHER_NAIVE_BOOST = 1.33
    # precalculated 4x4 Bayer Matrix / 16 - 0.5
    DITHER_BAYER_MATRIX = np.array([[-0.5   ,  0.    , -0.375 ,  0.125 ],
                                   [ 0.25  , -0.25  ,  0.375 , -0.125 ],
                                   [-0.3125,  0.1875, -0.4375,  0.0625],
                                   [ 0.4375, -0.0625,  0.3125, -0.1875]])
    
    def __init__(self, height=None, width=None, factor=None, upscale=1, 
                 depth=1, palette=8, dither="none", sobel=3,
                 alpha=.6, boost=True):
        if (width is not None or height is not None) and factor is not None:
            raise ValueError("You can only set either height + width or the downscaling factor, but not both!")
        assert height is None or height >= 1, "Width must be a positive integer!"
        assert width is None or width >= 1, "Width must be a positive integer!" 
        assert factor is None or factor >= 1, "Factor must be a positive integer!"
        assert isinstance(sobel, int) and sobel >= 2, "Sobel must be an integer strictly greater than 1!"
        self.height = int(height) if height else None
        self.width = int(width) if width else None
        self.factor = int(factor) if factor else None
        self.sobel = sobel
        if isinstance(upscale, (list, tuple, set, np.ndarray)):
            assert len(upscale) == 2, "Upscale must be len 2, with 2 positive integers!"
            assert upscale[0] >= 1 and upscale[1] >=1, "Upscale must have 2 positive values!"
            self.upscale = (upscale[0], upscale[1])
        else:    
            assert upscale >= 1, "Upscale must be a positive integer!"
            self.upscale = (upscale, upscale)
        assert depth > 0 and isinstance(depth, int), "Depth must be a positive integer!"
        if depth > 2:
            warnings.warn("Depth too high, it will probably take really long to finish!", Warning)
        self.depth = depth
        self.palette = palette
        self.find_palette = isinstance(self.palette, (int, float))  # palette is a number
        if self.find_palette and palette < 2:
            raise ValueError("The minimum number of colors in a palette is 2")
        elif not self.find_palette and len(palette) < 2:
            raise ValueError("The minimum number of colors in a palette is 2")
        assert dither in (None, "none", "naive", "bayer", "floyd", "atkinson"), "Unknown dithering algorithm!"
        self.dither = dither
        self.alpha = float(alpha)
        self.boost = bool(boost)
        
        self.model = BGM(self.palette, self.find_palette)
        self.is_fitted = False
        self.palette_cache = None
    
    def _get_size(self, original_height, original_width):
        """Calculate new size depending on settings"""
        if self.height is not None and self.width is not None:
            return self.height, self.width
        elif self.height is not None:
            return self.height, int(self.height / original_height * original_width)
        elif self.width is not None:
            return int(self.width / original_width * original_height), self.width
        elif self.factor is not None:
            return original_height // self.factor, original_width // self.factor
        else:
            return original_height, original_width

    def _image_to_float(self, image):
        """Helper function that changes 0-255 color representation to 0.-1."""
        if np.issubdtype(image.dtype, np.integer):
            return np.clip(np.array(image, dtype=float) / 255., 0, 1).astype(float)
        return image
    
    def _image_to_int(self, image):
        """Helper function that changes 0.-1. color representation to 0-255"""
        if isinstance(image, BasePalette):
            image = np.array(image.value, dtype=float)
        elif isinstance(image, (list, tuple)):
            is_int = np.all([isinstance(x, int) for x in image])
            if is_int:
                return np.clip(np.array(image, dtype=int), 0, 255)
            else:
                image = np.array(image, dtype=float)
        if image.dtype in (float, np.float, np.float32, np.float64):
            return np.clip(np.array(image, dtype=float) * 255., 0, 255).astype(int)
        return image
        
    @property
    def colors(self):
        """Get colors in palette"""
        if self.palette_cache is None:
            if self.find_palette:
                assert self.is_fitted, "Call 'fit(image_as_numpy)' first!"
                c = rgb2hsv(self.model.means_.reshape(-1, 1, 3))
                c[:, :, 1:] *= self.SCALE_RGB
                c = hsv2rgb(c)
                c = np.clip(c * 255 // self.COLOR_QUANT * self.COLOR_QUANT, 0, 255).astype(int)
                c[c < self.COLOR_QUANT * 2] = 0
                c[c > 255 - self.COLOR_QUANT * 2] = 255
                self.palette_cache = c
                if len(np.unique([f"{pc[0]}" for pc in self.palette_cache])) != len(c):
                    warnings.warn("Some colors are redundant, try a different palette size for better results!", Warning)
            else:
                self.palette_cache = self._image_to_int(self.palette)
        return self.palette_cache
    
    @property
    def _palette(self):
        """Get colors in palette as a plottable palette format"""
        return self._image_to_float(self.colors.reshape(-1, 3))
    
    def fit(self, X, y=None):
        """Fit palette and optionally calculate automatic dithering"""
        h, w, d = X.shape
        # create a smaller image for BGM without alpha channel
        if d > 3:
            # separate color and alpha channels
            X_ = self._dilate(X).reshape(-1, 4)
            alpha_mask = X_[:, 3]
            X_ = X_[alpha_mask >= self.alpha]
            X_ = X_.reshape(1, -1, 4)
            X_ = resize(X[:, :, :3], (1, min(h, self.BGM_RESIZE) * min(w, self.BGM_RESIZE)), anti_aliasing=False)
        else:
            X_ = resize(X[:, :, :3], (min(h, self.BGM_RESIZE), min(w, self.BGM_RESIZE)), anti_aliasing=False)
        X_ = self._image_to_float(X_).reshape(-1, 3)  # make sure colors have a float representation
        if self.find_palette:
            X_ = ((X_ - .5) * self.SCALE_RGB) + .5  # move values away from grayish colors 
        
        # fit BGM to generate palette
        self.model.fit(X_)
        self.is_fitted = True  # all done, user may call transform()
        return self

    def _pyxelate(self, X):
        """Downsample image based on the magnitude of its gradients in sobel-sided tiles"""

        @adapt_rgb(each_channel)
        def _wrapper(dim):
            h, w = dim.shape
            sobel = skimage_sobel(dim)
            sobel += 1e-8 # avoid division by zero
            sobel_norm = view_as_blocks(sobel, (self.sobel, self.sobel)).sum((2,3))
            sum_prod = view_as_blocks((sobel * dim), (self.sobel, self.sobel)).sum((2,3))
            return sum_prod / sobel_norm

        X_pad = self._pad(X, self.sobel)
        return _wrapper(X_pad).copy()
    
    def _pad(self, X, pad_size, nh=None, nw=None):
        """Pad image if it's not pad_size divisable or remove such padding"""
        if nh is None and nw is None:
            # pad edges so image is divisible by pad_size
            h, w, d = X.shape
            h1, h2 = (1 if h % pad_size > 0 else 0), (1 if h % pad_size == 1 else 0)
            w1, w2 = (1 if w % pad_size > 0 else 0), (1 if w % pad_size == 1 else 0)
            return np.pad(X, ((h1, h2), (w1, w2), (0, 0)), "edge")
        else:
            # remove previous padding
            return X[slice((1 if nh % pad_size > 0 else 0),(-1 if nh % pad_size == 1 else None)), 
                     slice((1 if nw % pad_size > 0 else 0),(-1 if nw % pad_size == 1 else None)), :]
    
    def _dilate(self, X):
        """Dilate semi-transparent edges to remove artifacts"""
        h, w, d = X.shape
        X_ = self._pad(X, 3)
        @adapt_rgb(each_channel)
        def _wrapper(dim):
            return skimage_dilation(dim, selem=skimage_square(3))
        mask = X_[:, :, 3]
        alter = _wrapper(X_[:, :, :3])
        X_[:, :, :3][mask < self.alpha] = alter[mask < self.alpha]
        return self._pad(X_, 3, h, w)
    
    def _median(self, X):
        """Median filter on HSV channels using 3x3 squares"""
        h, w, d = X.shape
        X_ = self._pad(X, 3)
        X_ = rgb2hsv(X_)
        @adapt_rgb(each_channel)
        def _wrapper(dim):
            return skimage_median(dim, skimage_square(3))
        X_ = _wrapper(X_)
        X_ = hsv2rgb(X_)
        return self._pad(X_, 3, h, w)

    def _warn_on_dither_with_alpha(self, d):
        if d > 3 and self.dither in ("bayer", "floyd", "atkinson"):
            warnings.warn("Images with transparency can have unwanted artifacts around the edges with this dithering method. Use 'naive' instead.", Warning)

    def transform(self, X, y=None):
        """Transform image to pyxelated version"""
        assert self.is_fitted, "Call 'fit(image_as_numpy)' first before calling 'transform(image_as_numpy)'!"
        h, w, d = X.shape
        if self.find_palette:
            assert h * w > self.palette, "Too many colors for such a small image! Use a larger image or a smaller palette."
        else:
            assert h * w > len(self.palette), "Too many colors for such a small image! Use a larger image or a smaller palette."
        
        new_h, new_w = self._get_size(h, w)  # get desired size depending on settings
        if d > 3:
            # image has alpha channel
            X_ = self._dilate(X)
            alpha_mask = resize(X_[:, :, 3], (new_h, new_w), anti_aliasing=True)
        else:
            # image has no alpha channel
            X_ = X
            alpha_mask = None
        if self.depth:
            # change size depending on the number of iterations
            new_h, new_w = new_h * (self.sobel ** self.depth), new_w * (self.sobel ** self.depth)
        X_ = resize(X_[:, :, :3], (new_h, new_w), anti_aliasing=True)  # colors are now 0. - 1.        
        
        if self.boost:
            # adjust contrast
            X_ = rgb2hsv(equalize_adapthist(X_))
            X_[:, :, 1:] *= self.HIST_BRIGHTNESS
            X_ = hsv2rgb(np.clip(X_, 0., 1.))
        
        # pyxelate iteratively
        for _ in range(self.depth):
            if self.boost and d == 3:
                # remove noise
                X_ = self._median(X_)
            X_ = self._pyxelate(X_)  # downsample in each iteration
            
        final_h, final_w, _ = X_.shape
        if self.find_palette:
            X_ = ((X_ - .5) * self.SCALE_RGB) + .5  # values were already altered before in .fit()
        reshaped = np.reshape(X_, (final_h * final_w, 3))
            
        # add dithering
        if self.dither is None or self.dither == "none":
            probs = self.model.predict(reshaped)
            X_ = self.colors[probs]
        elif self.dither == "naive":
            # pyxelate dithering based on BGM probability density
            probs = self.model.predict_proba(reshaped)
            p = np.argmax(probs, axis=1)
            X_ = self.colors[p]
            probs[np.arange(len(p)), p] = 0
            p2 = np.argmax(probs, axis=1)  # second best
            v1 = np.max(probs, axis=1) > (1.  / (len(self.colors) + 1))
            v2 = np.max(probs, axis=1) > (1.  / (len(self.colors) * self.DITHER_NAIVE_BOOST + 1))
            pad = not bool(final_w % 2)
            for i in range(0, len(X_), 2):
                m = (i // final_w) % 2
                if pad:
                    i += m
                if m:
                    if v1[i]:
                        X_[i] = self.colors[p2[i]]
                elif v2[i]:
                    X_[i] = self.colors[p2[i]]
        elif self.dither == "bayer":
            # Bayer-like dithering
            self._warn_on_dither_with_alpha(d)
            probs = self.model.predict_proba(reshaped)
            probs = [convolve(probs[:, i].reshape((final_h, final_w)), self.DITHER_BAYER_MATRIX, mode="reflect") for i in range(len(self.colors))]
            probs = np.argmin(probs, axis=0)
            X_ = self.colors[probs]
        elif self.dither == "floyd":
            # Floyd-Steinberg-like dithering
            self._warn_on_dither_with_alpha(d)
            probs = self.model.predict_proba(reshaped)
            probs = np.array([probs[:, i].reshape((final_h, final_w)) for i in range(len(self.colors))])
            #probs = 1. / np.where(probs == 1, 1., -np.log(probs))
            probs = np.power(probs, (1. / 6.))
            res = np.zeros((final_h, final_w), dtype=int)
            for y in range(final_h - 1):
                for x in range(1, final_w - 1):
                    quant_error = probs[:, y, x] / 16.
                    res[y, x] = np.argmax(quant_error)
                    quant_error[res[y, x]] = 0.
                    probs[:, y, x+1] += quant_error * 7.
                    probs[:, y+1, x-1] += quant_error * 3.
                    probs[:, y+1, x] += quant_error * 5.
                    probs[:, y+1, x+1] += quant_error
            # fix edges
            x = final_w - 1
            for y in range(final_h):
                res[y, x] = np.argmax(probs[:, y, x])
                res[y, 0] = np.argmax(probs[:, y, 0])
            y = final_h - 1
            for x in range(1, final_w - 1):
                res[y, x] = np.argmax(probs[:, y, x])
            X_ = self.colors[res.reshape(final_h * final_w)]   
        elif self.dither == "atkinson":
            # Atkinson-like algorithm
            self._warn_on_dither_with_alpha(d)
            res = np.zeros((final_h + 2, final_w + 3), dtype=int)
            X_ = np.pad(X_, ((0, 2), (1, 2), (0, 0)), "reflect")
            for y in range(final_h):
                for x in range(1, final_w+1):
                    pred = self.model.predict_proba(X_[y, x, :3].reshape(-1, 3))
                    res[y, x] = np.argmax(pred)
                    quant_error = (X_[y, x, :3] - self.model.means_[res[y, x]]) / 8.
                    X_[y, x+1, :3] += quant_error
                    X_[y, x+2, :3] += quant_error
                    X_[y+1, x-1, :3] += quant_error
                    X_[y+1, x, :3] += quant_error
                    X_[y+1, x+1, :3] += quant_error
                    X_[y+2, x, :3] += quant_error
            # fix edges
            res = res[:final_h, 1:final_w+1]
            X_ = self.colors[res.reshape(final_h * final_w)]
        
        X_ = np.reshape(X_, (final_h, final_w, 3))  # reshape to actual image dimensions
        if alpha_mask is not None:
            # attach lost alpha layer
            alpha_mask[alpha_mask >= self.alpha] = 255
            alpha_mask[alpha_mask < self.alpha] = 0
            X_ = np.dstack((X_[:, :, :3], alpha_mask.astype(int)))
        
        # return upscaled image
        X_ = np.repeat(np.repeat(X_, self.upscale[0], axis=0), self.upscale[1], axis=1)
        return X_.astype(np.uint8)
