FROM node:24.15.0-alpine
WORKDIR /frontend

# Copy package files first to leverage Docker cache
COPY package.json package-lock.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application
# (In dev, this is overridden by the volume mount)
COPY . .

# Expose Vite/React default development port
EXPOSE 5173

# Start the development server
# --host is required for Vite to be accessible outside the container
CMD ["npm", "run", "dev", "--", "--host"]